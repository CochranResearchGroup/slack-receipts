# Installed actions and response capture

Slack Receipts owns Slack rendering and interaction capture. Receipts owns
application routing and correlation; consumers use the hub rather than integrating
Slack callbacks. This child grants no credential or other domain authority.

## Owner enrollment

In the existing private workspace configuration, opt in explicitly:

```yaml
interactive:
  enabled: true
  app_id: A_EXAMPLE
  applications: [auth]
```

The workspace must also have its existing `team_id`, Socket Mode app token, bot
read/write credentials and frontend authentication. These are private installation
values; never put them in source or issues. The enrolled app ID must match the
Slack app associated with the Socket Mode token. Registration is owner-controlled;
only trusted frontend users should hold sessions that can install/send actions.
OS-user separation and the existing frontend session remain the custody boundary.
The consuming app gets no child cookie, private route or other app's identity.

Socket Mode templates now enable interactivity. Applying an updated Slack app
manifest/reinstalling and enabling private config are separate live operations;
source publication changes neither. No HTTP interaction callback is added. The
existing HTTP Events path remains unchanged.

## Hub-facing API

Authenticated same-origin `POST
/v1/workspaces/{workspace}/applications/{application}/interactive`, with a JSON
body of at most 64 KiB. The hub supplies the owner session cookie and child Origin.
Guest grants, anonymous callers and auth-disabled servers cannot use this route.
The configured workspace enrolls the application. Operations have exact keys:

- `{operation: "install", definition}` stores an immutable app/id/version definition.
- `{operation: "inspect", definition}` reads original installation confirmation.
- `{operation: "send", destination, request}` persists before a message send.
- `{operation: "receive", requestId}` repeatedly reads the original stored response.

Success returns `{ok: true, result}`. Installation result status is `installed` or
`unknown`; send status is `delivered` or `unknown`; receive returns zero or one
channel-neutral event. No operation lets HTTP callers assert an actor or action.

Definitions are `{id, version, actions}`. An action is `{id, label, payloadSchema}`.
The finite button subset supports closed object schemas with primitive properties;
required string/integer fields need explicit enums and required booleans may use
an explicit enum or both values. Optional fields are omitted from button payloads.
There are at most 16 actions/properties, 16 values per enum and 25 buttons total;
labels including values must fit 75 characters. Unsupported/free-text schemas fail
explicitly rather than rendering an unverifiable button. Four grant durations are
ordinary app-provided enum values, not Slack Receipts grant semantics.

A request is exactly `{requestId, idempotencyKey, actionSet, version, message,
expiresAt}`. Original request identity and meaning are immutable. The hub owns its
idempotency key and correlation; child custody is keyed by enrolled app/requestId.
Non-secret text up to 4096 characters is split across Slack sections as needed.
Buttons use opaque per-request IDs/nonces; response payloads come from the stored
original button definitions, not from user-supplied callback JSON.

## Capture and recovery

The existing Socket Mode SDK connection authenticates envelopes. Its dispatcher
checks team/app against enrollment and original request, exact original channel
and message timestamp, nonce, button identity, expiry and current app enrollment.
Actor comes from Slack's authenticated payload. A valid response is committed
before acknowledging the envelope. Storage failure leaves it unacknowledged for
retry. Invalid or stale interactions are acknowledged without a response. The
first committed response wins across duplicate/concurrent callbacks and restart.
Raw payloads, response URLs, Slack tokens and private errors are not stored in the
response. Receive returns `{id, requestId, applicationId, actionSet, version,
actor, action, payload}`; actor is `slack:<team>:<user>`.

The child claims a send before contacting Slack. Lost acknowledgement stays
`unknown`; reusing the original request never sends again. SDK automatic retries
are disabled for this interactive write. Without confirmed original message
identity, clicks cannot adopt a different message or resolve the unknown send.
Such requests stay held; there is no automatic resend or timeout approval. A
response does not establish application authorization or successful authentication.
Guarantees cover process restart, not arbitrary filesystem/power failure.

Slack references: [Socket Mode authentication and acknowledgements](https://docs.slack.dev/apis/events-api/using-socket-mode/),
[block action payloads](https://docs.slack.dev/reference/interaction-payloads/block_actions-payload/).

## Source validation

Run `uv run python -m unittest discover -s tests -v`. Tests use synthetic
workspaces/messages and real SQLite/API/Socket dispatch, replacing only external
Slack transport. They cover HTTP authentication/CSRF, correlation, immutable
versions, concurrency, restart/no-replay, wrong/stale/rotated identities and
persistence-before-ACK. They do not contact Slack or install an app.

The parent actual-source harness independently launches this child API and
Socket dispatcher with controlled Slack transport. Live installed-workspace
qualification remains separate from source integration.
