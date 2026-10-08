---
description: Make this device forget its Relebo token
allowed-tools: Bash(python3:*)
---

The token was already forgotten before you read this; the script's one line is below.

!`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/_login.py" --logout`

Repeat that line to the person verbatim. It deleted the token kept on this device only; remind
them that the token itself lives until they revoke it under Connections on the web, and that
`/relebo:login` connects the device again.
