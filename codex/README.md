# Relebo plugin for Codex

The same memory as in Claude Code, from Codex: the hooks are the same scripts, run as the
Codex client (`RELEBO_CLIENT=codex`), so the token the device gets is listed as Codex under
Connections. Claude Code and Codex on the same device share that token (`~/.relebo/token.json`).

This folder is the plugin's manifest and its `hooks/hooks.json`; the scripts themselves live in
`plugins/claude-code/relebo/hooks` and are copied in here when the plugins are released, so the
published plugin is whole on its own. Codex reads the marketplace at
`.agents/plugins/marketplace.json` of the published repository, which names this plugin.

## Install

```sh
codex plugin marketplace add Samprand/relebo-plugins
codex plugin add relebo@relebo
```

Codex asks you to trust the plugin's hooks the first time: accept. The first session opens
your browser on the approval page with the code filled in (where no browser can open, it shows
the link); approve, and the device is connected by itself. `codex plugin marketplace upgrade`
refreshes the marketplace; `codex plugin remove relebo@relebo` takes the plugin out — revoke the
device under Connections on the web to close it for good.

Not documented by OpenAI, and therefore not relied on here: environment variables for hooks
outside a plugin. Inside a plugin, `${PLUGIN_ROOT}` is the plugin's own folder, and that is
what the hook commands use.
