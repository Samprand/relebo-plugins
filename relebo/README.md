# Relebo plugin for Claude Code

The memory of your places in every Claude Code session. The hooks on this device hold no key to
anything: they tell the Relebo engine what they see (the repository's remote, the folder's name,
what you said, the action about to happen, what the turn changed) and the engine answers as you.

- **SessionStart**: what the place you are in remembers, and what holds everywhere.
- **UserPromptSubmit**: what your words bring to mind; what you said is read in the background.
- **PreToolUse**: an action is judged against the rules of the place before it runs. An action
  the memory cannot judge is put to you.
- **PostToolUse**: what the place remembers about what was just done.
- **Stop**: the lines the turn changed are reviewed; a question the reading opened is put.

## Logging in

Nothing of Relebo needs to be installed on the device. The first session shows one line:

> Relebo: to connect this device, approve code WDJB-MJHT at https://relebo.ai/device?code=WDJB-MJHT (the code lasts 15 minutes).

Open that address, sign in to Relebo as always (the one-time code by email), see what is asking
to come in ("Claude Code on your-mac") and press Approve. At your next message the session says
"Relebo: this device is connected as you." and the memory is on. Until then each prompt shows
"Relebo is waiting for code WDJB-MJHT at …". Nothing blocks the session in the meantime; it
only runs without the memory.

- A code nobody approves dies after fifteen minutes; the next session shows a new one.
- Deny on the web stops the asking for that session. `/relebo:login` asks again.
- Revoke the device under **Connections** on the web and the next hook throws the token away and
  shows a new code right then, saying when it was disconnected.

### Commands

- `/relebo:login` opens your browser on the approval page with a fresh code and waits for
  you to approve (where no browser can open, it shows the code and the address instead).
- `/relebo:status` says whether this device is connected and to which engine.
- `/relebo:logout` makes the device forget its token (revoke it under Connections too).

### Where things live

| What | Where |
|---|---|
| The token this device acts with, and the engine it belongs to | `~/.relebo/token.json` (mode 600) |
| A code asked for and not yet approved | `~/.relebo/device.json` |
| Where each project is on this device | `~/.relebo/memory/places.json` |
| The hooks' log | `~/.relebo/memory/hooks.log` |

### Settings and environment

Identity, first one found wins: the plugin option **Relebo token** (`CLAUDE_PLUGIN_OPTION_TOKEN`),
then `RELEBO_TOKEN`, then `~/.relebo/token.json`. Engine, first one found wins: the plugin option
**Engine URL** (`CLAUDE_PLUGIN_OPTION_ENGINE_URL`), then `RELEBO_ENGINE_URL`, then the engine
recorded in `token.json`, then the hosted engine. `RELEBO_CLIENT` names the client the hooks run
as (`claude-code` by default; Codex sets `codex`).
