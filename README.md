# Slack Receipts

Slack Receipts is a local-first Slack export, mirror, search, and runtime API
toolkit. It can mirror Slack workspaces into SQLite, keep a Socket Mode listener
running under user-scoped systemd services, expose local CLI/API/MCP surfaces,
and generate export/report artifacts from mirrored Slack data.

This public source release intentionally excludes private operator runbooks,
development plans, repo-local agent instructions, tenant fixtures, generated
exports, and local runtime state from the private development repository.

## Install

```bash
uv sync
uv run slack-receipts --help
```

For a managed local install:

```bash
uv run slack-receipts user-env install
```

Then edit `~/.config/slack-receipts/config.yaml`, install workspace
credentials into the configured dotenv file, sync the config, and install live
mode for each workspace that should run unattended.

## Configuration

Start from `config.example.yaml`. Runtime state is user-scoped by default:

- config: `~/.config/slack-receipts`
- state: `~/.local/state/slack-receipts`
- cache: `~/.local/cache/slack-receipts`
- exports: `~/.local/share/slack-receipts/exports`
- tenant artifacts:
  `~/.local/state/slack-receipts/tenants/<workspace>/`

Rendered per-tenant Slack app manifests are generated under the tenant artifact
root, not inside the source checkout.

## Slack Apps

The generic Socket Mode app templates live under `manifests/`. Use
`docs/SLACK_MANIFEST.md` for the app-manifest workflow and keep Slack tokens in
your user-scoped dotenv file, never in tracked source files.

## Documentation

- `docs/CONFIG.md`: configuration reference
- `docs/CLI.md`: CLI reference
- `docs/API_MCP_CONTRACT.md`: local API and MCP contract
- `docs/ARCHITECTURE.md`: architecture overview
- `docs/SLACK_MANIFEST.md`: Slack app manifest workflow

## Compatibility

The Python package is still named `slack_mirror` for compatibility with earlier
local deployments. Preferred console entry points use the Slack Receipts name,
while legacy Slack Mirror command aliases remain available where documented.

## License

See `LICENSE`.

## Routed application actions

Slack Receipts can install reusable action definitions for owner-enrolled
applications, render message buttons and persist attributable responses received
through authenticated Socket Mode. The parent Receipts hub owns user-scoped
routing and the application's send/receive interface. Domain authorization stays
with the consuming application. See [interactive actions](docs/INTERACTIVE_ACTIONS.md).

This is source functionality. Updating templates does not update an installed
Slack app, enable private configuration or send messages. Live installation and
acceptance require a separately bounded operator task.
