---
description: Connect this device to Relebo as you
allowed-tools: Bash(python3:*)
---

The login already ran before you read this: the person's browser opened on the approval page
with the code filled in, and a watcher keeps the token the moment they approve. Its one line
is below.

!`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/_login.py" --connect`

Repeat that line to the person verbatim: the code and the address exactly as printed, nothing
rephrased. If the line names a code to approve, then run this one command, once, and nothing
else:

`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/_login.py" --wait`

It returns when the person approves, or after two minutes at most. Tell the person the line
it prints, verbatim. Do not run it again, do not poll, and never ask them to paste anything.
