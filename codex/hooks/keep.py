"""The agent's call on a label of the memory's block (R1, R2…): keep what the signal
carried, confirm or drop a proposal, answer a question. What happened is printed back,
line by line: the only truth about what was kept (decided 2026-11-17: «el agente manda a
guardar; si va a fallar, que el agente se entere»).

    python3 keep.py --session <id> --label R1 --text "<the memory's own words>"
        [--work]                       a piece of work asked, born planned
        [--confirmed]                  the person said yes to this label
        [--drop]                       nothing to keep, or the person said no
        [--said "<their words>"]       the person's choice (whose, where)
        [--place NAME --what "<what it is>" --repo owner/name]…   a place, repeated
        [--chain "bigger > smaller > smallest"]
    python3 keep.py --session <id> --text "<your own words>"      with no label
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client

HOOK = "keep"
NOT_SENT = "not kept: %s"


def parse(argv: list):
    body: dict = {"places": [], "chain": []}
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--session" and rest:
            body["origin_id"] = rest.pop(0)
        elif arg == "--label" and rest:
            body["label"] = rest.pop(0)
        elif arg == "--text" and rest:
            body["text"] = rest.pop(0)
        elif arg == "--said" and rest:
            body["said"] = rest.pop(0)
        elif arg == "--work":
            body["kind"] = "work"
        elif arg == "--confirmed":
            body["confirmed"] = True
        elif arg == "--drop":
            body["drop"] = True
        elif arg == "--place" and rest:
            body["places"].append({"name": rest.pop(0)})
        elif arg == "--what" and rest and body["places"]:
            body["places"][-1]["description"] = rest.pop(0)
        elif arg == "--repo" and rest and body["places"]:
            body["places"][-1]["repo"] = rest.pop(0)
        elif arg == "--chain" and rest:
            body["chain"] = [n.strip() for n in rest.pop(0).split(">") if n.strip()]
        else:
            return None
    if not body.get("origin_id") or not (body.get("label") or body.get("text")):
        return None
    return body


def main(argv: list) -> int:
    body = parse(argv)
    if body is None:
        print(__doc__)
        return 2
    if not _client.identified():
        print(NOT_SENT % "this device is not connected to Relebo")
        return 1
    reply = _client.post_reply("/memory/sessions/act", body, timeout=_client.TIMEOUT_S)
    if not reply.ok:
        _client.log(HOOK + " refused: " + str(reply.status))
        print(NOT_SENT % ("the engine answered " + str(reply.status)))
        return 1
    print((reply.body or {}).get("context") or "nothing happened")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
