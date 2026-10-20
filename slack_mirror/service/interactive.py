"""Child-owned action definitions, Slack rendering and Socket Mode capture.

Only capture from the authenticated Socket Mode dispatcher may assert actors.
The HTTP API deliberately exposes no actor/action ingestion operation.
"""
import itertools
import json
import re
import secrets
import time
from slack_mirror.core.slack_api import SlackApiClient


def token(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value) is not None


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def choices(definition):
    """Compile the bounded finite payload-schema subset into exact buttons."""
    if not isinstance(definition, dict) or set(definition) != {'id', 'version', 'actions'} or not token(definition['id']) or type(definition['version']) is not int or not 1 <= definition['version'] <= 9007199254740991:
        raise ValueError('invalid_action_set')
    if len(canonical(definition).encode()) > 16384 or not isinstance(definition['actions'], list) or not 1 <= len(definition['actions']) <= 16:
        raise ValueError('invalid_action_set')
    result, ids = [], set()
    for action in definition['actions']:
        if not isinstance(action, dict) or set(action) != {'id', 'label', 'payloadSchema'} or not token(action['id']) or action['id'] in ids or not isinstance(action['label'], str) or not 1 <= len(action['label']) <= 75:
            raise ValueError('invalid_action')
        ids.add(action['id'])
        schema = action['payloadSchema']
        if not isinstance(schema, dict) or set(schema) - {'type', 'properties', 'required', 'additionalProperties'} or schema.get('type') != 'object' or schema.get('additionalProperties') is not False or not isinstance(schema.get('properties'), dict) or len(schema['properties']) > 16:
            raise ValueError('unsupported_action_schema')
        required = schema.get('required', [])
        if not isinstance(required, list) or len(set(required)) != len(required) or any(key not in schema['properties'] for key in required):
            raise ValueError('invalid_required_fields')
        for key, rule in schema['properties'].items():
            if not token(key) or not isinstance(rule, dict) or set(rule) - {'type', 'enum'} or rule.get('type') not in ('string', 'integer', 'boolean'):
                raise ValueError('unsupported_action_schema')
        values = []
        for key in required:
            rule = schema['properties'][key]
            enums = rule.get('enum', [False, True] if rule['type'] == 'boolean' else None)
            expected = {'string': str, 'integer': int, 'boolean': bool}[rule['type']]
            if not isinstance(enums, list) or not 1 <= len(enums) <= 16 or any(type(item) is not expected or (isinstance(item, str) and len(item) > 128) or (type(item) is int and abs(item) > 9007199254740991) for item in enums):
                raise ValueError('buttons_require_bounded_enum_fields')
            values.append(enums)
        # Bound expansion before materializing it.
        count = 1
        for items in values:
            count *= len(items)
        if len(result) + count > 25:
            raise ValueError('too_many_buttons')
        for combination in itertools.product(*values):
            payload = dict(zip(required, combination))
            label = action['label'] + (': ' + ', '.join(map(str, combination)) if combination else '')
            if len(label) > 75:
                raise ValueError('button_label_too_long')
            result.append({'action': action['id'], 'label': label, 'payload': payload})
    return result


class InteractiveActions:
    def __init__(self, service, now=None):
        self.service = service
        self.now = now or (lambda: int(time.time() * 1000))

    def enrolled(self, conn, workspace, application=None):
        config = self.service.workspace_config_by_name(workspace)
        settings = config.get('interactive', {})
        if settings.get('enabled') is not True or not token(settings.get('app_id')) or not token(config.get('team_id')):
            raise ValueError('interactive_not_enrolled')
        if application is not None and (not token(application) or application not in settings.get('applications', [])):
            raise ValueError('application_not_enrolled')
        return self.service.workspace_id(conn, workspace), config['team_id'], settings['app_id']

    def install(self, conn, workspace, application, definition):
        workspace_id, _, _ = self.enrolled(conn, workspace, application)
        choices(definition)
        encoded = canonical(definition)
        with conn:
            conn.execute('INSERT OR IGNORE INTO interactive_definitions VALUES(?,?,?,?,?)', (workspace_id, application, definition['id'], definition['version'], encoded))
            original = conn.execute('SELECT definition FROM interactive_definitions WHERE workspace_id=? AND application=? AND id=? AND version=?', (workspace_id, application, definition['id'], definition['version'])).fetchone()
            if original['definition'] != encoded:
                raise ValueError('action_set_conflict')
        return {'status': 'installed'}

    def installed(self, conn, workspace, application, definition):
        workspace_id, _, _ = self.enrolled(conn, workspace, application)
        row = conn.execute('SELECT definition FROM interactive_definitions WHERE workspace_id=? AND application=? AND id=? AND version=?', (workspace_id, application, definition['id'], definition['version'])).fetchone()
        return {'status': 'installed' if row and row['definition'] == canonical(definition) else 'unknown'}

    def send(self, conn, workspace, application, destination, body):
        workspace_id, team_id, app_id = self.enrolled(conn, workspace, application)
        if not isinstance(body, dict) or set(body) != {'requestId', 'idempotencyKey', 'actionSet', 'version', 'message', 'expiresAt'} or not all(token(body[key]) for key in ('requestId', 'idempotencyKey', 'actionSet')) or type(body['version']) is not int or not 1 <= body['version'] <= 9007199254740991 or not isinstance(body['message'], str) or not 1 <= len(body['message']) <= 4096 or type(body['expiresAt']) is not int or not 1 <= body['expiresAt'] <= 9007199254740991:
            raise ValueError('invalid_request')
        original = conn.execute('SELECT * FROM interactive_requests WHERE workspace_id=? AND application=? AND request_id=?', (workspace_id, application, body['requestId'])).fetchone()
        if original:
            if original['body'] != canonical(body):
                raise ValueError('idempotency_conflict')
            return {'status': original['delivery']}
        if body['expiresAt'] <= self.now():
            raise ValueError('request_expired')
        row = conn.execute('SELECT definition FROM interactive_definitions WHERE workspace_id=? AND application=? AND id=? AND version=?', (workspace_id, application, body['actionSet'], body['version'])).fetchone()
        if not row:
            raise ValueError('action_set_not_installed')
        client = SlackApiClient(self.service.workspace_token(workspace, purpose='write'), max_rate_limit_retries=0)
        client.client.retry_handlers = []
        channel = self.service.resolve_outbound_channel(conn, workspace_id=workspace_id, channel_ref=destination, client=client)
        nonce = secrets.token_hex(24)
        buttons = {secrets.token_hex(16): value for value in choices(json.loads(row['definition']))}
        with conn:
            claim = conn.execute('INSERT OR IGNORE INTO interactive_requests VALUES(?,?,?,?,?,?,?,?,NULL,NULL,?,?)', (workspace_id, application, body['requestId'], canonical(body), channel, nonce, canonical(buttons), 'unknown', team_id, app_id))
        if not claim.rowcount:
            return self.send(conn, workspace, application, destination, body)
        elements = [{'type': 'button', 'text': {'type': 'plain_text', 'text': value['label']}, 'action_id': key, 'value': nonce} for key, value in buttons.items()]
        blocks = [{'type': 'section', 'text': {'type': 'plain_text', 'text': body['message'][i:i+3000]}} for i in range(0, len(body['message']), 3000)]
        blocks.extend({'type': 'actions', 'block_id': nonce, 'elements': elements[i:i+5]} for i in range(0, len(elements), 5))
        try:
            response = client.send_message(channel=channel, text=body['message'], blocks=blocks)
            if response.get('ok') and response.get('channel') == channel and isinstance(response.get('ts'), str):
                with conn:
                    conn.execute("UPDATE interactive_requests SET delivery='delivered', message_ts=? WHERE workspace_id=? AND application=? AND request_id=?", (response['ts'], workspace_id, application, body['requestId']))
        except Exception:
            # Do not expose provider errors or retry an effect with lost acknowledgement.
            pass
        return {'status': conn.execute('SELECT delivery FROM interactive_requests WHERE workspace_id=? AND application=? AND request_id=?', (workspace_id, application, body['requestId'])).fetchone()['delivery']}

    def receive(self, conn, workspace, application, request_id):
        workspace_id, _, _ = self.enrolled(conn, workspace, application)
        row = conn.execute('SELECT response FROM interactive_requests WHERE workspace_id=? AND application=? AND request_id=?', (workspace_id, application, request_id)).fetchone()
        return [json.loads(row['response'])] if row and row['response'] else []

    def capture(self, conn, workspace, envelope_id, payload):
        workspace_id, team, app = self.enrolled(conn, workspace)
        if not token(envelope_id) or not isinstance(payload, dict) or payload.get('type') != 'block_actions' or (payload.get('team') or {}).get('id') != team or payload.get('api_app_id') != app:
            return False
        container, actions = payload.get('container') or {}, payload.get('actions') or []
        actor = (payload.get('user') or {}).get('id')
        if not token(actor) or container.get('type') != 'message' or len(actions) != 1 or actions[0].get('type') != 'button':
            return False
        action = actions[0]
        row = conn.execute('SELECT * FROM interactive_requests WHERE workspace_id=? AND nonce=?', (workspace_id, action.get('block_id'))).fetchone()
        if not row or row['team_id'] != team or row['app_id'] != app or row['channel'] != container.get('channel_id') or action.get('value') != row['nonce'] or not row['message_ts'] or row['message_ts'] != container.get('message_ts') or not isinstance(container.get('message_ts'), str):
            return False
        try:
            self.enrolled(conn, workspace, row['application'])
        except ValueError:
            return False
        body, buttons = json.loads(row['body']), json.loads(row['buttons'])
        button = buttons.get(action.get('action_id'))
        if not button or body['expiresAt'] <= self.now():
            return False
        event = {'id': envelope_id, 'requestId': row['request_id'], 'applicationId': row['application'], 'actionSet': body['actionSet'], 'version': body['version'], 'actor': f'slack:{team}:{actor}', 'action': button['action'], 'payload': button['payload']}
        with conn:
            conn.execute("UPDATE interactive_requests SET response=?, delivery='delivered', message_ts=? WHERE workspace_id=? AND application=? AND request_id=? AND response IS NULL", (canonical(event), container['message_ts'], workspace_id, row['application'], row['request_id']))
        return True
