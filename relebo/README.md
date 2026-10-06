# Relebo plugin for Claude Code

The memory of your places in every Claude Code session. The hooks on this machine hold no key
to anything: they tell the Relebo engine what they see (the repository's remote, the folder's
name, what you said, the action about to happen, what the turn changed) and the engine answers
as you, by your machine's key or your session token.

- **SessionStart**: what the place you are in remembers, and what holds everywhere.
- **UserPromptSubmit**: what your words bring to mind; what you said is read in the background.
- **PreToolUse**: an action is judged against the rules of the place before it runs. An action
  the memory cannot judge is put to you.
- **PostToolUse**: what the place remembers about what was just done.
- **Stop**: the lines the turn changed are reviewed; a question the reading opened is put.

Where each project is on this machine is kept in `~/.relebo/memory/places.json`; the hooks'
log is `~/.relebo/memory/hooks.log`.
