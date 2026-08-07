# -*- coding: utf-8 -*-
"""Caption Confluence image attachments (diagrams/screenshots) with Claude vision,
so they become searchable text in the index and can be shown with answers.
Degrades gracefully to no caption when no API key / unsupported type."""
import os
import base64

_MEDIA = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
          "gif": "image/gif", "webp": "image/webp"}

IMAGE_EXT = set(_MEDIA)

_PROMPT = (
    "This image is from MobiFin Tapestry product documentation{ctx}. "
    "If it is a DIAGRAM (architecture, network, data flow, sequence, ER, deployment), "
    "describe what it depicts: the components/nodes, any layers or zones, and how they "
    "connect or flow. If it is a UI SCREENSHOT, describe the feature and key elements. "
    "Be factual and concise (max ~150 words). "
    "If it is only a logo or purely decorative, reply with exactly: DECORATIVE"
)


def available():
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def caption_image(image_bytes, filename, context=""):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    media = _MEDIA.get(ext)
    if not media or not available():
        return ""
    try:
        import anthropic
        model = os.getenv("TAPESTRY_VISION_MODEL",
                          os.getenv("TAPESTRY_LLM_MODEL", "claude-sonnet-4-5"))
        b64 = base64.b64encode(image_bytes).decode("ascii")
        prompt = _PROMPT.format(ctx=f" (page: {context})" if context else "")
        msg = anthropic.Anthropic().messages.create(
            model=model, max_tokens=400,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
                {"type": "text", "text": prompt}]}])
        txt = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        return "" if txt.upper().startswith("DECORATIVE") else txt
    except Exception:
        return ""
