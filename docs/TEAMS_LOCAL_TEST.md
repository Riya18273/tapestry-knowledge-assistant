# Teams — quick test from your local laptop (ngrok)

Test the "Ask Tapestry" Teams chatbot from your laptop, no server needed. A tunnel (ngrok)
gives Teams a temporary public HTTPS URL that relays to your local API.

> ⚠️ **Testing only.** The bot works only while your laptop **and** ngrok are running; free ngrok
> URLs change on each restart. For always-on team use, deploy on the server (DEPLOYMENT.md §7b)
> or Azure (§7c).
>
> ⚠️ **Network:** your office proxy blocked tunnel tools earlier (cloudflared/dev-tunnels 403). If
> ngrok is blocked too, run this on **home Wi-Fi or a mobile hotspot**.

## Prerequisites
- API running locally (Ollama up + index built) — `GET /api/v1/health` shows `engine: ollama`.
- A free **ngrok** account (ngrok.com) + your authtoken.
- **Team-owner** rights to add an Outgoing Webhook in the target team.

## Steps
**1. Terminal 1 — run the API (leave open):**
```bash
cd /d D:\tapestry-knowledge-assistant && python -m uvicorn api:app --port 8000
```

**2. Install ngrok** (download from ngrok.com/download on an open network), then set your token:
```bash
ngrok config add-authtoken <your-token>
```

**3. Terminal 2 — start the tunnel:**
```bash
ngrok http 8000
```
Copy the printed `https://<random>.ngrok-free.app`.

**4. Create the Teams Outgoing Webhook** (team owner):
Team → **••• → Manage team → Apps → Create an outgoing webhook** →
**Callback URL** = `https://<random>.ngrok-free.app/api/v1/teams` → name `AskTapestry` → **Create**
→ copy the **security token**.

**5. Wire the secret** into `D:\tapestry-knowledge-assistant\.env`:
```
TAPESTRY_TEAMS_SECRET=<paste the token>
TAPESTRY_TEAMS_PERSONA=engineer
```
Then **restart** the API (Ctrl+C in Terminal 1, re-run).

**6. Ask in the team:**
```
@AskTapestry what changed in release 1.0.1?
@AskTapestry [customer] what's new for me?
```
Answers come from local `llama3.2` — **$0**.

## Gotchas
- **Restarted ngrok?** The URL changed → update the webhook's Callback URL.
- **401 from the endpoint?** The token in `.env` doesn't match, or you didn't restart the API after setting it.
- **No reply?** Check Terminal 1 for the incoming `POST /api/v1/teams`; confirm the ngrok URL is the exact `.../api/v1/teams`.
- **Office network blocks ngrok?** Use home Wi-Fi / hotspot for the test.
