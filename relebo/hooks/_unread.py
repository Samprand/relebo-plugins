"""A prompt the engine could not read when it came (a row held, a timeout, a 500) is kept on
this device and sent again before the next call that reads words, so the person's words are
never lost to the memory. On 2026-10-16 "el 8 descártalo. 9 no lo entiendo" came back 503
and was read by nobody: the rule it discarded stood on. Stdlib only, as every hook."""

from __future__ import annotations

import _client

UNREAD_FILE = _client.MEMORY_DIR / "unread.json"
# more than this waiting is a session the engine cannot hear at all: the oldest go
MAX_WAITING = 5


def keep(session_id: str, text: str) -> None:
    text = (text or "").strip()
    if not session_id or not text:
        return
    waiting = _client.read_json(UNREAD_FILE)
    texts = [t for t in waiting.get(session_id) or [] if isinstance(t, str)]
    texts.append(text)
    waiting[session_id] = texts[-MAX_WAITING:]
    _client.write_json(UNREAD_FILE, waiting)
    _client.log("prompt kept unread for " + session_id + ": " + text[:80])


def flush(session_id: str, place: dict) -> None:
    """Every prompt of the session still unread, sent in order; one that fails again stays,
    and nothing after it is sent, so the order of the person's words holds."""
    waiting = _client.read_json(UNREAD_FILE)
    texts = [t for t in waiting.get(session_id) or [] if isinstance(t, str)]
    if not texts:
        return
    left = list(texts)
    for text in texts:
        reply = _client.post_reply(
            "/memory/sessions/prompt", {"origin_id": session_id, "text": text, **place}
        )
        if not reply.ok:
            break
        left.pop(0)
        _client.log("unread prompt read for " + session_id + ": " + text[:80])
    if left:
        waiting[session_id] = left
    else:
        waiting.pop(session_id, None)
    _client.write_json(UNREAD_FILE, waiting)
