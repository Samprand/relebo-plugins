"""The person's work in Relebo from a shell, for an agent whose plugin carries no tools
(Codex): what each tool is and takes, and one call.

    python3 work.py                          the tools, each with its description and input
    python3 work.py <tool> '<json input>'    one call; the answer is JSON
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _client
import _work

NO_TOOLS = "no work tools: %s"
BAD_INPUT = "the input is not a JSON object: %s"


def main(argv: list) -> int:
    if not argv:
        listed = _work.tools()
        if not listed:
            # the call says why: not connected, not reached, or signed in before the tools
            print(NO_TOOLS % _work.call("list_workspaces", {}))
            return 1
        print(json.dumps(listed, ensure_ascii=False, indent=1))
        return 0
    try:
        arguments = json.loads(argv[1]) if len(argv) > 1 else {}
    except ValueError as error:
        print(BAD_INPUT % error)
        return 2
    if not isinstance(arguments, dict):
        print(BAD_INPUT % argv[1])
        return 2
    print(_work.call(argv[0], arguments))
    return 0 if _client.identified() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
