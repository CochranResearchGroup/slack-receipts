# Slack App Manifest Workflow (Private Multi-Workspace)

Use one manifest template and create one private app per workspace (no public distribution review).
For live Slack Mirror installs, prefer the Socket Mode manifest so the local service does not need a public Slack Events request URL.

## Files

- Preferred live-mode template: `manifests/slack-mirror-socket-mode.json`
- YAML equivalent: `manifests/slack-mirror-socket-mode.yaml`
- Renderer: `scripts/render_slack_manifest.py`
- Rendered output examples:
  - `~/.local/state/slack-receipts/tenants/acme/manifests/slack-app-manifest.rendered.json`

Prefer JSON for Slack's copy/paste app-manifest flow. YAML is supported by Slack, but JSON is less brittle in browser text areas and chat/terminal copy paths.

## 1) Render a workspace-specific manifest

For a managed install, prefer the tenant wizard because it renders the JSON manifest and creates a disabled workspace scaffold in one step:

```bash
slack-mirror-user tenants onboard \
  --name acme \
  --domain acme-example \
  --display-name "Acme Example"
```

The same flow is available from the authenticated browser settings page:

- `http://slack.localhost/settings/tenants`

After the required credentials are installed into the configured dotenv file, activate the tenant with:

```bash
slack-mirror-user tenants activate acme
```

For a live Socket Mode workspace:

```bash
export SLACK_MIRROR_APP_NAME="Slack Mirror Acme"
export SLACK_MIRROR_BOT_DISPLAY_NAME="Slack Mirror"
export SLACK_MIRROR_REDIRECT_URL="https://localhost:3000/slack/oauth/callback"

python3 scripts/render_slack_manifest.py \
  --template manifests/slack-mirror-socket-mode.json \
  --output ~/.local/state/slack-receipts/tenants/acme/manifests/slack-app-manifest.rendered.json
```

The older HTTP Events manifest path has been retired from this repo. Use the Socket Mode templates only.

## 2) Create the Slack app

1. Go to `https://api.slack.com/apps`.
2. Click **Create New App**.
3. Choose **From an app manifest**.
4. Select the target workspace.
5. Paste the rendered manifest JSON, for example `~/.local/state/slack-receipts/tenants/acme/manifests/slack-app-manifest.rendered.json`.
6. Create the app.

## 3) Install the app and collect credentials

In the Slack app settings:

- **Basic Information**:
  - copy **Signing Secret** into `SLACK_<WORKSPACE>_SIGNING_SECRET`
  - note the app's workspace/team identifier if Slack shows it; otherwise obtain it with `auth.test` after token setup
- **OAuth & Permissions**:
  - click **Install to Workspace** or **Reinstall to Workspace**
  - copy **Bot User OAuth Token** (`xoxb-...`) into:
    - `SLACK_<WORKSPACE>_BOT_TOKEN`
    - `SLACK_<WORKSPACE>_WRITE_BOT_TOKEN`
  - if you enabled user scopes and installed user-token access, copy **User OAuth Token** (`xoxp-...`) into:
    - `SLACK_<WORKSPACE>_USER_TOKEN`
    - `SLACK_<WORKSPACE>_WRITE_USER_TOKEN`
- **Socket Mode**:
  - confirm Socket Mode is enabled by the manifest
  - create an app-level token with `connections:write`
  - copy the app-level token (`xapp-...`) into `SLACK_<WORKSPACE>_APP_TOKEN`

The canonical Socket Mode manifest includes `files:read` in both bot and user
scopes. Keep it in user scopes: Slack Mirror's user-auth reconcile path needs a
user token that can call `files.info` and download user-visible private files.

The canonical Socket Mode manifest includes `reactions:write` in both bot and
user scopes. Keep it in both places: Slack Mirror reaction status signals can
run with either `auth_mode: bot` or `auth_mode: user`. Existing apps must be
reinstalled or reauthorized before Slack grants the new scope; updating the
local manifest file alone is not enough.

The canonical Socket Mode manifest also includes the outbound conversation
scopes needed for MCP/API message sends by user reference:

- `channels:write`
- `groups:write`
- `im:write`
- `mpim:write`

It also enables the App Home Messages tab by default. For the current Slack Mirror outbound DM flow, that tab must stay enabled; otherwise Slack can reject app-user sends with `messages_tab_disabled`.

If you update an existing app from an older manifest, reinstall the app after applying the new manifest so Slack grants the additional scopes.

For a workspace named `acme`, use these variable names:

```bash
SLACK_ACME_TEAM_ID=
SLACK_ACME_BOT_TOKEN=
SLACK_ACME_WRITE_BOT_TOKEN=
SLACK_ACME_USER_TOKEN=
SLACK_ACME_WRITE_USER_TOKEN=
SLACK_ACME_APP_TOKEN=
SLACK_ACME_SIGNING_SECRET=
```

## 4) Install credentials

Do not put Slack secrets directly in tracked repo files.

For this managed install, `~/.config/slack-mirror/config.yaml` loads:

```yaml
dotenv: ~/credentials/API-keys.env
```

Prefer the product credential installer so onboarding does not require hand-editing dotenv syntax:

```bash
slack-mirror-user tenants credentials acme \
  --credential team_id=T... \
  --credential token=xoxb-... \
  --credential outbound_token=xoxb-... \
  --credential user_token=xoxp-... \
  --credential outbound_user_token=xoxp-... \
  --credential app_token=xapp-... \
  --credential signing_secret=...
```

The accepted field names are `team_id`, `token`, `outbound_token`, `user_token`, `outbound_user_token`, `app_token`, and `signing_secret`.
The command maps them to the deterministic `SLACK_<WORKSPACE>_*` variables, writes or updates the configured dotenv file, creates a timestamped backup when replacing an existing file, and reports only redacted readiness.
It also accepts the env var names directly, for example `--credential SLACK_ACME_BOT_TOKEN=xoxb-...`.

The authenticated browser page at `http://slack.localhost/settings/tenants` provides the same local credential-install path.

Manual fallback is to edit the dotenv file directly:

```bash
cat >> ~/credentials/API-keys.env <<'EOF'
SLACK_ACME_TEAM_ID=T...
SLACK_ACME_BOT_TOKEN=xoxb-...
SLACK_ACME_WRITE_BOT_TOKEN=xoxb-...
SLACK_ACME_USER_TOKEN=xoxp-...
SLACK_ACME_WRITE_USER_TOKEN=xoxp-...
SLACK_ACME_APP_TOKEN=xapp-...
SLACK_ACME_SIGNING_SECRET=...
EOF
```

If one token is intentionally shared for read and write, repeat the same value in both variables. Keeping separate variable names makes the read/write contract explicit and keeps `workspaces verify --require-explicit-outbound` meaningful.

## 5) Activate the workspace

Keep the workspace disabled until the credentials exist:

```yaml
workspaces:
  - name: acme
    domain: acme-example
    team_id: ${SLACK_ACME_TEAM_ID:-}
    token: ${SLACK_ACME_BOT_TOKEN:-}
    outbound_token: ${SLACK_ACME_WRITE_BOT_TOKEN:-}
    user_token: ${SLACK_ACME_USER_TOKEN:-}
    outbound_user_token: ${SLACK_ACME_WRITE_USER_TOKEN:-}
    app_token: ${SLACK_ACME_APP_TOKEN:-}
    signing_secret: ${SLACK_ACME_SIGNING_SECRET:-}
    enabled: false
```

After the env vars are present, prefer the activation command:

```bash
slack-mirror-user tenants activate acme
```

That command sets `enabled: true`, syncs config into the DB, and installs or refreshes live units after required credentials are present.
Manual fallback:

```bash
slack-mirror-user workspaces sync-config
slack-mirror-user workspaces verify --workspace acme --require-explicit-outbound
scripts/install_live_mode_systemd_user.sh acme
slack-mirror-user user-env check-live --json
```

Repeat the same process for each workspace. Keep one manifest template; only rendered app name and credentials differ per workspace.
