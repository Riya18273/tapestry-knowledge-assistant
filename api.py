# -*- coding: utf-8 -*-
"""Tapestry "Ask MobiFin" RAG service — a thin FastAPI wrapper over the existing
engine. One shared backend for every channel; also serves an internal web chat at /.

Endpoints:
  GET  /                      — internal "Ask Tapestry" web chat (HTML)
  GET  /api/v1/health         — status, vector count, active answer engine
  GET  /api/v1/personas       — persona list for the UI
  POST /api/v1/chat           — grounded answer (persona-scoped, confidence-gated)
  POST /api/v1/ingest         — (re)build the KB (background) then rebuild the index
  GET  /api/v1/ingest/status  — ingest progress
  GET  /api/v1/documents      — indexed KB summary
  GET  /api/v1/image/{name}   — serve a captioned diagram image (from data/images)

Zero-credit by default: TAPESTRY_LLM_MODE=local (Ollama), embeddings local, and the
confidence gate refuses weak matches so no LLM is called at all.
Run:  uvicorn api:app --host 0.0.0.0 --port 8000
"""
import os
import re
import json
import hmac
import base64
import hashlib
import secrets
import threading
from typing import Optional, List

from fastapi import FastAPI, BackgroundTasks, Response, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel

import answer
import auth
import ingest
import vectorstore
import personas
import config

app = FastAPI(title="Tapestry Ask MobiFin API", version="1.0")

# In-memory sessions: token -> {"username":..., "personas":[...]}. No SSO required —
# the SERVER decides a user's persona from who they authenticated as; a client can no
# longer just claim to be "engineer" once TAPESTRY_AUTH_REQUIRED is on. Ephemeral by
# design ($0, no DB): lost on restart, fine at this scale (see docs/DEPLOYMENT.md).
_SESSIONS = {}


def _session_from(request):
    tok = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    return _SESSIONS.get(tok)

_IMG_DIR = os.path.join(config.settings()["data_dir"], "images")
_VISUAL = ("show", "diagram", "image", "picture", "visual", "screenshot", "flowchart",
           "flow chart", "mockup", "wireframe", "mailer", "illustration", "figure",
           "display", "see the", "what does it look")

_ingest_lock = threading.Lock()
_ingest_state = {"running": False, "last": None}


def _run_ingest(sources, rebuild, incremental):
    try:
        if incremental and set(sources) <= {"confluence"}:
            _ingest_state["last"] = ingest.ingest_incremental()      # embed only changed pages
        else:
            counts = ingest.ingest(sources=tuple(sources))
            vectors = vectorstore.build() if rebuild else vectorstore.stats().get("vectors", 0)
            _ingest_state["last"] = {"mode": "full", "ingested": counts, "vectors": vectors}
    except Exception as e:  # noqa: BLE001
        _ingest_state["last"] = {"error": str(e)}
    finally:
        _ingest_state["running"] = False
        _ingest_lock.release()


# ------------------------------------------------------------------ models --
class ChatIn(BaseModel):
    question: str
    persona: str = "engineer"
    product: Optional[str] = None
    release: Optional[str] = None
    issue_id: Optional[str] = None
    page_url: Optional[str] = None


class ChatOut(BaseModel):
    answer: Optional[str]
    sources: List[dict]
    confidence: float
    fallback_used: bool
    provider: str


class IngestIn(BaseModel):
    sources: List[str] = ["confluence"]
    rebuild: bool = True
    incremental: bool = True      # confluence: re-embed only new/changed pages


class LoginIn(BaseModel):
    username: str
    password: str


# --------------------------------------------------------------- endpoints --
@app.get("/api/v1/health")
def health():
    eng, detail = answer.engine_status()
    return {"status": "ok", "vectors": vectorstore.stats().get("vectors", 0),
            "engine": eng, "engine_detail": detail, "min_confidence": answer.min_confidence()}


@app.get("/api/v1/personas")
def personas_list():
    return [{"id": k, "label": v} for k, v in personas.labels().items()]


@app.get("/api/v1/auth-status")
def auth_status():
    return {"required": auth.enabled()}


@app.post("/api/v1/login")
def login(inp: LoginIn):
    result = auth.authenticate(inp.username, inp.password)
    if not result:
        return JSONResponse({"detail": "Invalid username or password"}, status_code=401)
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = result
    return {"token": token, "username": result["username"], "personas": result["personas"]}


@app.get("/api/v1/me")
def me(request: Request):
    sess = _session_from(request)
    if not sess:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return {"username": sess["username"], "personas": sess["personas"]}


@app.post("/api/v1/chat", response_model=ChatOut)
def chat(inp: ChatIn, request: Request):
    persona = inp.persona
    if auth.enabled():
        sess = _session_from(request)
        if not sess:
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        if persona not in sess["personas"]:      # server decides — client can't claim a persona
            return JSONResponse(
                {"detail": f"Persona '{persona}' not permitted for this account"},
                status_code=403)
    ctx = " ".join(x for x in (inp.release, inp.issue_id) if x)
    q = f"{inp.question} (context: {ctx})" if ctx else inp.question
    r = answer.answer(q, persona)
    visual = any(w in inp.question.lower() for w in _VISUAL)   # show images only if asked
    srcs = []
    for s in r.get("sources", []):
        ip = s.pop("image_path", None)                          # never leak local FS paths
        if visual and ip and os.path.exists(ip):
            s["image_url"] = "/api/v1/image/" + os.path.basename(ip)
        srcs.append(s)
    return {"answer": r.get("answer"), "sources": srcs,
            "confidence": r.get("confidence", 0.0),
            "fallback_used": r.get("fallback_used", False),
            "provider": r.get("provider", "")}


@app.post("/api/v1/ingest")
def ingest_endpoint(inp: IngestIn, background: BackgroundTasks):
    if not _ingest_lock.acquire(blocking=False):
        return {"status": "already_running", "documents": ingest.stats()}
    _ingest_state["running"] = True
    background.add_task(_run_ingest, inp.sources, inp.rebuild, inp.incremental)
    return {"status": "started", "note": "runs in background; poll GET /api/v1/ingest/status"}


@app.get("/api/v1/ingest/status")
def ingest_status():
    return {"running": _ingest_state["running"], "last": _ingest_state["last"],
            "documents": ingest.stats()}


@app.get("/api/v1/documents")
def documents():
    return ingest.stats()


@app.get("/api/v1/image/{name}")
def image(name: str):
    if "/" in name or "\\" in name or ".." in name:      # no path traversal
        return Response(status_code=400)
    p = os.path.join(_IMG_DIR, name)
    if not os.path.isfile(p):
        return Response(status_code=404)
    return FileResponse(p)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home():
    return _CHAT_HTML


# ------------------------------------------------- Teams Outgoing Webhook --
_PERSONA_ALIAS = {"cxo": "executive", "exec": "executive", "sales": "sales_marketing",
                  "marketing": "sales_marketing", "pm": "product_manager",
                  "product manager": "product_manager", "dev": "engineer",
                  "developer": "engineer"}


def _clean_teams_text(t):
    t = re.sub(r"(?is)<at>.*?</at>", " ", t or "")   # drop the @bot mention
    t = re.sub(r"<[^>]+>", " ", t)
    return " ".join(t.split()).strip()


def _persona_from(text, default):
    """Allow '[sales] question' or 'engineer: question' to pick a persona for testing."""
    m = re.match(r"\s*[\[]?\s*([a-z /]+?)\s*[\]:]\s*(.+)$", text, re.I)
    if m:
        key = m.group(1).strip().lower()
        pid = _PERSONA_ALIAS.get(key, key.replace(" ", "_"))
        if pid in personas.PERSONAS:
            return pid, m.group(2).strip()
    return default, text


@app.post("/api/v1/teams", include_in_schema=False)
async def teams(request: Request):
    body = await request.body()
    secret = os.getenv("TAPESTRY_TEAMS_SECRET", "")
    if secret:                                        # verify HMAC-SHA256 (base64 secret)
        try:
            mac = hmac.new(base64.b64decode(secret), body, hashlib.sha256).digest()
            expected = "HMAC " + base64.b64encode(mac).decode()
        except Exception:
            expected = None
        provided = request.headers.get("authorization", "")
        if not expected or not hmac.compare_digest(expected, provided):
            return JSONResponse({"type": "message", "text": "Unauthorized."}, status_code=401)

    data = json.loads(body or b"{}")
    question = _clean_teams_text(data.get("text", ""))
    if not question:
        return JSONResponse({"type": "message", "text": "Ask me a question about Tapestry."})
    persona, question = _persona_from(question, os.getenv("TAPESTRY_TEAMS_PERSONA", "engineer"))
    r = answer.answer(question, persona)
    reply = r.get("answer") or "I couldn't find an answer in the Product KB."
    srcs = [s["title"] for s in r.get("sources", []) if s.get("title")][:4]
    if srcs:
        reply += "\n\n**Sources:** " + ", ".join(srcs)
    return JSONResponse({"type": "message", "text": reply})


# --------------------------------------------------------------- web chat --
_CHAT_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ask Tapestry</title>
<style>
 :root{--navy:#0E1E36;--blue:#2E6BF0;--bg:#f4f6fa;--card:#fff;--ink:#16202e;--muted:#5a6675;--line:#e2e7ef;--chip:#eaf0fb}
 *{box-sizing:border-box} body{margin:0;font-family:"Segoe UI",system-ui,Arial,sans-serif;background:var(--bg);color:var(--ink)}
 header{background:linear-gradient(135deg,var(--navy),#132a4a);color:#fff;padding:14px 20px;display:flex;align-items:center;gap:12px}
 header b{font-size:18px} header span{color:#9fb6da;font-size:12px}
 .wrap{max-width:860px;margin:0 auto;padding:16px}
 #log{display:flex;flex-direction:column;gap:14px;margin-bottom:14px}
 .msg{padding:12px 14px;border-radius:12px;max-width:92%}
 .u{align-self:flex-end;background:var(--navy);color:#fff}
 .a{align-self:flex-start;background:var(--card);border:1px solid var(--line);width:100%}
 .a h4{margin:.4em 0 .2em;font-size:15px;color:var(--navy)} .a p{margin:.4em 0;line-height:1.5}
 .a ul{margin:.25em 0;padding-left:1.3em} .a li{margin:.2em 0} .a li>ul{margin:.2em 0}
 .a code{background:#eef;padding:1px 5px;border-radius:5px;font-size:.9em}
 .meta{margin-top:8px;font-size:12px;color:var(--muted);display:flex;gap:8px;flex-wrap:wrap;align-items:center}
 .chip{background:var(--chip);color:#1e4fb0;border-radius:10px;padding:2px 9px;font-size:11px}
 .src{margin-top:8px;font-size:12.5px;color:var(--muted);border-top:1px solid var(--line);padding-top:8px}
 .src a{color:var(--blue);text-decoration:none} .a img{max-width:100%;border:1px solid var(--line);border-radius:8px;margin:8px 0}
 .row{position:sticky;bottom:0;background:var(--bg);padding:10px 0;display:flex;gap:8px}
 select,input,button{font:inherit} select{padding:9px;border:1px solid var(--line);border-radius:10px;background:#fff}
 input{flex:1;padding:11px 13px;border:1px solid var(--line);border-radius:10px}
 button{background:var(--blue);color:#fff;border:0;border-radius:10px;padding:0 18px;cursor:pointer}
 button:disabled{opacity:.5;cursor:default}
 .hint{color:var(--muted);font-size:12px;margin:2px 0 12px}
</style></head><body>
<header><b>Ask Tapestry</b><span id="eng">·</span></header>
<div class="wrap">
  <div id="loginBox" style="display:none">
    <div class="hint">Sign in to use Ask Tapestry.</div>
    <div class="row">
      <input id="luser" placeholder="username" autocomplete="username">
      <input id="lpass" type="password" placeholder="password" autocomplete="current-password">
      <button id="loginBtn">Sign in</button>
    </div>
    <div id="loginErr" style="color:#c0392b;font-size:13px;margin-top:6px"></div>
  </div>
  <div id="chatBox">
    <div class="hint">Grounded answers from the Tapestry knowledge base. Pick who's asking, then ask a question.</div>
    <div id="log"></div>
    <div class="row">
      <select id="persona"></select>
      <input id="q" placeholder="e.g. What is new in the latest release?" autocomplete="off">
      <button id="send">Ask</button>
    </div>
  </div>
</div>
<script>
const log=document.getElementById('log'), qi=document.getElementById('q'),
      ps=document.getElementById('persona'), btn=document.getElementById('send');
const esc=s=>s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const inl=s=>esc(s).replace(/\\*\\*(.+?)\\*\\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>');
function render(t){
  // supports one level of nested/indented sub-bullets (tab or 2+ spaces, marker -/bullet/star/+/1.)
  // — many answers use a top-level bullet followed by a tab-indented "+" sub-bullet line,
  // which the old flat-list renderer dropped into plain paragraph tags, losing structure.
  let h='',topOpen=false,liOpen=false,subOpen=false;
  const closeAll=()=>{if(subOpen){h+='</ul>';subOpen=false;}if(liOpen){h+='</li>';liOpen=false;}
    if(topOpen){h+='</ul>';topOpen=false;}};
  for(const raw of (t||'').split('\\n')){
    const lead=(raw.match(/^[\\t ]*/)||[''])[0];
    const indent=(lead.match(/\\t/g)||[]).length+Math.floor(lead.replace(/\\t/g,'').length/2);
    const l=raw.trim();
    if(!l){closeAll();continue;}
    const m=l.match(/^(?:[-•*+]|\\d+[.)])\\s+(.*)/);
    if(m){
      if(indent>0&&liOpen){
        if(!subOpen){h+='<ul>';subOpen=true;}
        h+='<li>'+inl(m[1])+'</li>';
      }else{
        if(subOpen){h+='</ul>';subOpen=false;}
        if(liOpen)h+='</li>';
        if(!topOpen){h+='<ul>';topOpen=true;}
        h+='<li>'+inl(m[1]);liOpen=true;
      }
      continue;
    }
    closeAll();
    if(/^#{1,6}\\s/.test(l))h+='<h4>'+inl(l.replace(/^#{1,6}\\s/,''))+'</h4>';
    else if(/^sources:/i.test(l))h+='<div class="src">'+inl(l)+'</div>';
    else h+='<p>'+inl(l)+'</p>';
  }
  closeAll();
  return h;
}
function add(cls,html){const d=document.createElement('div');d.className='msg '+cls;d.innerHTML=html;log.appendChild(d);d.scrollIntoView({behavior:'smooth',block:'end'});return d;}

// --- auth (optional — only enforced if the server has TAPESTRY_AUTH_REQUIRED on).
// No SSO: the server maps username -> allowed persona(s); the client can no longer
// just claim to be "engineer" once this is on. Token lives in sessionStorage only
// (cleared when the tab closes), not localStorage.
let TOKEN=sessionStorage.getItem('tap_token')||null, MY_PERSONAS=null, ALL_PERSONAS=[];
const loginBox=document.getElementById('loginBox'), chatBox=document.getElementById('chatBox'),
      luser=document.getElementById('luser'), lpass=document.getElementById('lpass'),
      loginBtn=document.getElementById('loginBtn'), loginErr=document.getElementById('loginErr');

function showChat(){
  loginBox.style.display='none'; chatBox.style.display='';
  const opts=ALL_PERSONAS.filter(p=>!MY_PERSONAS||MY_PERSONAS.includes(p.id));
  ps.innerHTML=opts.map(p=>`<option value="${p.id}">${p.label}</option>`).join('');
  const eng=opts.findIndex(p=>p.id==='engineer'); if(eng>=0)ps.selectedIndex=eng;
  qi.focus();
}
async function doLogin(){
  loginErr.textContent=''; loginBtn.disabled=true;
  try{
    const r=await fetch('/api/v1/login',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:luser.value.trim(),password:lpass.value})});
    if(!r.ok){loginErr.textContent='Invalid username or password.';loginBtn.disabled=false;return;}
    const d=await r.json();
    TOKEN=d.token; MY_PERSONAS=d.personas; sessionStorage.setItem('tap_token',TOKEN);
    showChat();
  }catch(e){loginErr.textContent='Login failed: '+e;}
  loginBtn.disabled=false;
}
async function boot(){
  try{const h=await (await fetch('/api/v1/health')).json();
    document.getElementById('eng').textContent='· engine: '+h.engine+' · '+h.vectors+' passages';}catch(e){}
  ALL_PERSONAS=await (await fetch('/api/v1/personas')).json();
  const st=await (await fetch('/api/v1/auth-status')).json();
  if(!st.required){showChat();return;}
  if(TOKEN){
    const me=await fetch('/api/v1/me',{headers:{'Authorization':'Bearer '+TOKEN}});
    if(me.ok){MY_PERSONAS=(await me.json()).personas;showChat();return;}
    TOKEN=null; sessionStorage.removeItem('tap_token');
  }
  loginBox.style.display=''; chatBox.style.display='none'; luser.focus();
}
async function ask(){
  const q=qi.value.trim(); if(!q)return; qi.value='';
  add('u',esc(q)); const a=add('a','<em>Thinking…</em>'); btn.disabled=true;
  try{
    const headers={'Content-Type':'application/json'};
    if(TOKEN)headers['Authorization']='Bearer '+TOKEN;
    const resp=await fetch('/api/v1/chat',{method:'POST',headers,
      body:JSON.stringify({question:q,persona:ps.value})});
    if(resp.status===401){a.innerHTML='<span style="color:#c0392b">Session expired — refresh and sign in again.</span>';btn.disabled=false;return;}
    if(resp.status===403){a.innerHTML='<span style="color:#c0392b">That persona isn\\'t permitted for your account.</span>';btn.disabled=false;return;}
    const r=await resp.json();
    let html=render(r.answer||'(no answer)');
    (r.sources||[]).forEach(s=>{ if(s.image_url) html+=`<img src="${s.image_url}" alt="${esc(s.title||'')}">`; });
    html+=`<div class="meta"><span class="chip">confidence ${(r.confidence||0).toFixed(2)}</span>`+
          `<span class="chip">${esc(r.provider||'')}</span>`+(r.fallback_used?'<span class="chip">fallback</span>':'')+`</div>`;
    const srcs=(r.sources||[]).filter(s=>s.title);
    if(srcs.length)html+='<div class="src"><b>Sources:</b> '+srcs.map(s=>s.url?`<a href="${s.url}" target="_blank">${esc(s.title)}</a>`:esc(s.title)).join(' · ')+'</div>';
    a.innerHTML=html;
  }catch(e){a.innerHTML='<span style="color:#c0392b">Error: '+esc(String(e))+'</span>';}
  btn.disabled=false; qi.focus();
}
btn.onclick=ask; qi.addEventListener('keydown',e=>{if(e.key==='Enter')ask();});
loginBtn.onclick=doLogin; lpass.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();});
boot();
</script></body></html>"""
