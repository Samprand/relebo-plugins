"""What an agent reports to Relebo's maintainers: what the memory did wrong or doubtfully,
in the agent's words, with the session for the trace. The person hears a line from the
agent; the detail goes here, to the Maintainers' Pendientes.

    python3 feedback.py --session <session id> "what happened, why it looks wrong, the ids"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client

HOOK = "feedback"
SENT = "sent to Relebo's maintainers (pending %s)"
NOT_SENT = "not sent: %s"


def main(argv: list) -> int:
    session, words, memory_ids = "", [], []
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--session" and rest:
            session = rest.pop(0)
        elif arg == "--memory" and rest:
            memory_ids.append(int(rest.pop(0)))
        else:
            words.append(arg)
    text = " ".join(words).strip()
    if not text:
        print(__doc__)
        return 2
    if not _client.identified():
        print(NOT_SENT % "this device is not connected to Relebo")
        return 1
    reply = _client.post_reply(
        "/memory/sessions/feedback",
        {"origin_id": session, "text": text, "memory_ids": memory_ids},
        timeout=_client.TIMEOUT_S,
    )
    if not reply.ok:
        _client.log(HOOK + " not sent: " + str(reply.status))
        print(NOT_SENT % ("the engine answered " + str(reply.status)))
        return 1
    print(SENT % ((reply.body or {}).get("context") or "?"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
