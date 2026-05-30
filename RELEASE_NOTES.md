# Slack Receipts v0.3.0

Release date: 2026-05-30

## Included

- Local-first Slack mirror, search, export, API, and MCP source release.
- Preferred `slack-receipts` console command with legacy Slack Mirror
  compatibility aliases retained.
- User-scoped runtime defaults under Slack Receipts config, state, cache, and
  export roots.
- Generic Slack app manifest workflow and public configuration documentation.
- Public CLI, API/MCP, architecture, and Slack manifest documentation.

## Excluded From This Public Source Release

- Private development plans, runbook, and repo-local agent instructions.
- Tenant fixtures, generated exports, rendered tenant manifests, and local
  runtime state.
- Private scanner reports and private source history.
- Unsanitized tests. Public-safe fixtures and tests will be restored in a later
  public update.

## Compatibility

The Python package and import path remain `slack_mirror` for compatibility with
earlier local deployments. The preferred user-facing command name is
`slack-receipts`.

## Install Smoke

```bash
uv sync
uv run slack-receipts --help
```

## Known Limitations

- This release is source-only and is not a PyPI package publication.
- The first public tree intentionally omits private operational archaeology and
  unsanitized fixtures.
- Managed live Slack operation still requires locally supplied Slack app
  credentials in user-scoped configuration files.

## Security Review

This release must be generated from the private development repository through
`scripts/build_public_release_tree.sh` and must pass static private-surface
checks plus scanner-backed candidate review before publication.
