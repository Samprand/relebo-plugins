"""Look through the person's memory by words, from the agent's hand: what matches, with
its number, kind and words (2026-11-17: the agent checks instead of assuming).

    python3 search.py --session <session id> "<words>" [--workspace <id>]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client

HOOK = "search"
NOT_SEARCHED = "not searched: %s"
NOTHING = "nothing in the memory matches those words"


def main(argv: list) -> int:
    session, words, workspace = "", [], ""
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--session" and rest:
            session = rest.pop(0)
        elif arg == "--workspace" and rest:
            workspace = rest.pop(0)
        else:
            words.append(arg)
    query = " ".join(words).strip()
    if not query:
        print(__doc__)
        return 2
    if not _client.identified():
        print(NOT_SEARCHED % "this device is not connected to Relebo")
        return 1
    body = {"origin_id": session, "query": query}
    if workspace:
        body["workspace_id"] = int(workspace)
    reply = _client.post_reply("/memory/search", body, timeout=_client.TIMEOUT_S)
    if not reply.ok:
        _client.log(HOOK + " refused: " + str(reply.status))
        print(NOT_SEARCHED % ("the engine answered " + str(reply.status)))
        return 1
    print((reply.body or {}).get("context") or NOTHING)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
