import json
import tempfile
import unittest
import threading
import requests
from pathlib import Path
from unittest.mock import patch
from slack_mirror.service.app import SlackMirrorAppService
from slack_mirror.service.interactive import InteractiveActions

DEFINITION = {'id': 'review', 'version': 1, 'actions': [
    {'id': 'accept', 'label': 'Accept', 'payloadSchema': {'type': 'object', 'properties': {'duration': {'type': 'string', 'enum': ['once', 'hour', 'day', 'standing']}}, 'required': ['duration'], 'additionalProperties': False}},
    {'id': 'decline', 'label': 'Decline', 'payloadSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
]}

class InteractiveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name)
        config = path / 'config.yaml'
        config.write_text(f'''version: 1
storage:
  db_path: {path / 'state.sqlite'}
workspaces:
  - name: fixture
    team_id: TSYNTHETIC
    token: synthetic
    app_token: synthetic
    outbound_token: synthetic
    interactive:
      enabled: true
      app_id: ASYNTHETIC
      applications: [auth, reports]
''')
        self.config_path = str(config)
        config.write_text(config.read_text() + 'service:\n  auth:\n    enabled: true\n    allow_registration: true\n    cookie_secure_mode: never\n')
        self.service = SlackMirrorAppService(str(config))
        self.conn = self.service.connect()
        self.addCleanup(self.conn.close)
        self.actions = InteractiveActions(self.service)
        self.request = {'requestId': 'request-1', 'idempotencyKey': 'key-1', 'actionSet': 'review', 'version': 1, 'message': 'Synthetic review', 'expiresAt': 2000000000000}

    def send(self):
        self.actions.install(self.conn, 'fixture', 'auth', DEFINITION)
        with patch('slack_mirror.service.interactive.SlackApiClient') as api:
            api.return_value.send_message.return_value = {'ok': True, 'channel': 'CSYNTHETIC', 'ts': '100.001'}
            with patch.object(self.service, 'resolve_outbound_channel', return_value='CSYNTHETIC'):
                result = self.actions.send(self.conn, 'fixture', 'auth', 'CSYNTHETIC', self.request)
            self.blocks = api.return_value.send_message.call_args.kwargs['blocks']
        return result

    def payload(self):
        block = self.blocks[1]
        button = block['elements'][0]
        return {'type': 'block_actions', 'team': {'id': 'TSYNTHETIC'}, 'api_app_id': 'ASYNTHETIC', 'user': {'id': 'USYNTHETIC'},
            'container': {'type': 'message', 'channel_id': 'CSYNTHETIC', 'message_ts': '100.001'},
            'actions': [{'type': 'button', 'block_id': block['block_id'], 'action_id': button['action_id'], 'value': button['value']}]}

    def test_install_send_and_authenticated_correlated_button_response(self):
        self.assertEqual(self.send()['status'], 'delivered')
        self.assertEqual(len(self.blocks[1]['elements']), 5)
        self.assertTrue(self.actions.capture(self.conn, 'fixture', 'envelope-1', self.payload()))
        result = self.actions.receive(self.conn, 'fixture', 'auth', 'request-1')
        self.assertEqual(result, [{'id': 'envelope-1', 'requestId': 'request-1', 'applicationId': 'auth', 'actionSet': 'review', 'version': 1,
            'actor': 'slack:TSYNTHETIC:USYNTHETIC', 'action': 'accept', 'payload': {'duration': 'once'}}])
        self.assertEqual(self.actions.receive(self.conn, 'fixture', 'reports', 'request-1'), [])

    def test_seven_buttons_use_unique_block_ids_and_all_remain_clickable(self):
        definition = json.loads(json.dumps(DEFINITION))
        definition['actions'][0]['payloadSchema']['properties']['duration']['enum'] += ['five-minutes', 'eight-hours']
        with patch.dict(DEFINITION, definition):
            self.send()
        blocks = [block for block in self.blocks if block['type'] == 'actions']
        self.assertEqual(sum(len(block['elements']) for block in blocks), 7)
        self.assertEqual(len({block['block_id'] for block in blocks}), len(blocks))
        self.assertTrue(all(len(block['elements']) <= 25 for block in blocks))
        block = blocks[-1]
        button = block['elements'][-1]
        payload = self.payload()
        payload['actions'] = [{'type': 'button', 'block_id': block['block_id'], 'action_id': button['action_id'], 'value': button['value']}]
        self.assertTrue(self.actions.capture(self.conn, 'fixture', 'seven-button-click', payload))
        self.assertEqual(self.actions.receive(self.conn, 'fixture', 'auth', 'request-1')[0]['action'], 'decline')

    def test_rejected_stale_forged_and_wrong_message_actions_never_become_responses(self):
        self.send()
        for changed in [ {'team': {'id': 'TOTHER'}}, {'api_app_id': 'AOTHER'}, {'user': {'id': ''}},
                {'container': {'type': 'message', 'channel_id': 'COTHER', 'message_ts': '100.001'}},
                {'container': {'type': 'message', 'channel_id': 'CSYNTHETIC', 'message_ts': '999.001'}},
                {'actions': [{**self.payload()['actions'][0], 'value': 'forged'}]},
                {'actions': [{**self.payload()['actions'][0], 'action_id': 'forged'}]} ]:
            self.assertFalse(self.actions.capture(self.conn, 'fixture', 'rejected', {**self.payload(), **changed}))
        self.assertEqual(self.actions.receive(self.conn, 'fixture', 'auth', 'request-1'), [])
        config = self.service.workspace_config_by_name('fixture')
        with patch.object(self.service, 'workspace_config_by_name', return_value={**config, 'interactive': {**config['interactive'], 'applications': []}}):
            self.assertFalse(self.actions.capture(self.conn, 'fixture', 'removed-app', self.payload()))
        expired = InteractiveActions(self.service, now=lambda: 2000000000000)
        self.assertFalse(expired.capture(self.conn, 'fixture', 'expired', self.payload()))
        self.assertTrue(self.actions.capture(self.conn, 'fixture', 'original', self.payload()))
        original = self.actions.receive(self.conn, 'fixture', 'auth', 'request-1')
        self.actions.capture(self.conn, 'fixture', 'duplicate', {**self.payload(), 'user': {'id': 'UOTHER'}})
        self.assertEqual(self.actions.receive(self.conn, 'fixture', 'auth', 'request-1'), original)

    def test_unknown_send_cannot_adopt_an_unverified_message_or_retry_after_restart(self):
        self.actions.install(self.conn, 'fixture', 'auth', DEFINITION)
        with patch('slack_mirror.service.interactive.SlackApiClient') as api:
            def lost_ack(**kwargs):
                self.blocks = kwargs['blocks']
                raise OSError('lost acknowledgement')
            api.return_value.send_message.side_effect = lost_ack
            with patch.object(self.service, 'resolve_outbound_channel', return_value='CSYNTHETIC'):
                self.assertEqual(self.actions.send(self.conn, 'fixture', 'auth', 'CSYNTHETIC', self.request)['status'], 'unknown')
            peer = self.service.connect()
            self.addCleanup(peer.close)
            self.assertEqual(InteractiveActions(self.service).send(peer, 'fixture', 'auth', 'CSYNTHETIC', self.request)['status'], 'unknown')
            self.assertEqual(api.return_value.send_message.call_count, 1)
        self.assertFalse(self.actions.capture(self.conn, 'fixture', 'unverified-message', self.payload()))

    def test_socket_dispatch_persists_before_acknowledgement_and_retries_storage_failure(self):
        from types import SimpleNamespace
        from slack_mirror.service.server import dispatch_socket_request
        self.send()
        request = SimpleNamespace(type='interactive', envelope_id='socket-envelope', payload=self.payload())
        observed = []
        class Client:
            def send_socket_mode_response(inner, response):
                observed.append(self.actions.receive(self.conn, 'fixture', 'auth', 'request-1'))
        dispatch_socket_request(Client(), request, on_event=lambda event: None,
            on_interactive=lambda event_id, payload: self.actions.capture(self.conn, 'fixture', event_id, payload))
        self.assertEqual(observed[0][0]['id'], 'socket-envelope')
        def broken(event_id, payload):
            raise OSError('storage unavailable')
        with self.assertRaises(OSError):
            dispatch_socket_request(Client(), request, on_event=lambda event: None, on_interactive=broken)
        self.assertEqual(len(observed), 1)

    def test_authenticated_http_install_send_and_response_readback(self):
        from slack_mirror.service.api import create_api_server
        server = create_api_server(bind='127.0.0.1', port=0, config_path=self.config_path)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def stop():
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.addCleanup(stop)
        base = f'http://127.0.0.1:{server.server_address[1]}'
        url = base + '/v1/workspaces/fixture/applications/auth/interactive'
        self.assertEqual(requests.post(url, json={'operation': 'install', 'definition': DEFINITION}, timeout=3).status_code, 401)
        session = requests.Session()
        registered = session.post(base + '/auth/register', json={'username': 'synthetic-owner', 'password': 'synthetic-password-123', 'display_name': 'Synthetic owner'}, headers={'Origin': base}, timeout=3)
        self.assertEqual(registered.status_code, 201, registered.text)
        session.headers['Origin'] = base
        cross_origin = session.post(url, json={'operation': 'install', 'definition': DEFINITION}, headers={'Origin': 'https://untrusted.example'}, timeout=3)
        self.assertEqual(cross_origin.status_code, 403)
        installed = session.post(url, json={'operation': 'install', 'definition': DEFINITION}, timeout=3)
        self.assertEqual(installed.status_code, 200, installed.text)
        self.assertEqual(installed.json()['result']['status'], 'installed')
        with patch('slack_mirror.service.interactive.SlackApiClient') as api, patch('slack_mirror.service.app.SlackMirrorAppService.resolve_outbound_channel', return_value='CSYNTHETIC'):
            api.return_value.send_message.return_value = {'ok': True, 'channel': 'CSYNTHETIC', 'ts': '100.001'}
            sent = session.post(url, json={'operation': 'send', 'destination': 'CSYNTHETIC', 'request': self.request}, timeout=3)
            self.assertEqual(sent.status_code, 200, sent.text)
            self.blocks = api.return_value.send_message.call_args.kwargs['blocks']
        self.actions.capture(self.conn, 'fixture', 'http-action', self.payload())
        result = session.post(url, json={'operation': 'receive', 'requestId': 'request-1'}, timeout=3)
        self.assertEqual(result.json()['result'][0]['actor'], 'slack:TSYNTHETIC:USYNTHETIC')
        forged = session.post(url, json={'operation': 'capture', 'actor': 'USYNTHETIC'}, timeout=3)
        self.assertEqual(forged.status_code, 400)

    def test_rotated_app_identity_cannot_adopt_an_old_message(self):
        self.send()
        original_config = self.service.workspace_config_by_name('fixture')
        changed_config = {**original_config, 'interactive': {**original_config['interactive'], 'app_id': 'AROTATED'}}
        with patch.object(self.service, 'workspace_config_by_name', return_value=changed_config):
            self.assertFalse(self.actions.capture(self.conn, 'fixture', 'rotated', {**self.payload(), 'api_app_id': 'AROTATED'}))

    def test_immutable_definitions_and_concurrent_senders_preserve_one_channel_effect(self):
        self.actions.install(self.conn, 'fixture', 'auth', DEFINITION)
        with self.assertRaisesRegex(ValueError, 'action_set_conflict'):
            self.actions.install(self.conn, 'fixture', 'auth', {**DEFINITION, 'actions': [DEFINITION['actions'][1]]})
        peer = self.service.connect()
        self.addCleanup(peer.close)
        observed = []
        with patch('slack_mirror.service.interactive.SlackApiClient') as api:
            def concurrent(**kwargs):
                observed.append(InteractiveActions(self.service).send(peer, 'fixture', 'auth', 'CSYNTHETIC', self.request))
                return {'ok': True, 'channel': 'CSYNTHETIC', 'ts': '100.001'}
            api.return_value.send_message.side_effect = concurrent
            self.assertEqual(self.actions.send(self.conn, 'fixture', 'auth', 'CSYNTHETIC', self.request)['status'], 'delivered')
            self.assertEqual(observed, [{'status': 'unknown'}])
            self.assertEqual(api.return_value.send_message.call_count, 1)
        with self.assertRaisesRegex(ValueError, 'idempotency_conflict'):
            self.actions.send(peer, 'fixture', 'auth', 'CSYNTHETIC', {**self.request, 'message': 'altered'})

    def test_long_nonsecret_messages_fit_slack_section_limits(self):
        self.request['message'] = 'x' * 4096
        self.send()
        texts = [block['text']['text'] for block in self.blocks if block['type'] == 'section']
        self.assertEqual(''.join(texts), self.request['message'])
        self.assertTrue(all(len(value) <= 3000 for value in texts))

    def test_confirmed_response_updates_original_message_and_removes_buttons(self):
        self.send()
        self.actions.capture(self.conn, 'fixture', 'confirmation-event', self.payload())
        original = self.actions.receive(self.conn, 'fixture', 'auth', 'request-1')
        with patch('slack_mirror.service.interactive.SlackApiClient') as api:
            api.return_value.client.chat_update.return_value = {'ok': True, 'channel': 'CSYNTHETIC', 'ts': '100.001'}
            result = self.actions.confirm_message(self.conn, 'fixture', 'auth', 'request-1')
            self.assertEqual(result, {'status': 'confirmed'})
            update = api.return_value.client.chat_update.call_args.kwargs
            self.assertEqual((update['channel'], update['ts']), ('CSYNTHETIC', '100.001'))
            self.assertFalse(any(block['type'] == 'actions' for block in update['blocks']))
            self.assertIn('Response recorded', json.dumps(update['blocks']))
            self.actions.confirm_message(self.conn, 'fixture', 'auth', 'request-1')
            self.assertEqual(api.return_value.client.chat_update.call_count, 1)
        self.assertEqual(self.actions.receive(self.conn, 'fixture', 'auth', 'request-1'), original)

    def test_confirmation_runs_after_socket_ack_and_reconciles_lost_update_ack(self):
        from types import SimpleNamespace
        from slack_mirror.service.server import dispatch_socket_request
        self.send()
        order = []
        request = SimpleNamespace(type='interactive', envelope_id='confirmed', payload=self.payload())
        client = SimpleNamespace(send_socket_mode_response=lambda value: order.append('ack'))
        with patch('slack_mirror.service.interactive.SlackApiClient') as api:
            def lost_ack(**kwargs):
                order.append('update')
                raise OSError('lost update acknowledgement')
            api.return_value.client.chat_update.side_effect = lost_ack
            dispatch_socket_request(client, request, on_event=lambda value: None,
                on_interactive=lambda identity, payload: self.actions.capture(self.conn, 'fixture', identity, payload),
                after_interactive=lambda payload: self.actions.confirm_interaction(self.conn, 'fixture', payload))
            self.assertEqual(order, ['ack', 'update'])
            original = self.actions.receive(self.conn, 'fixture', 'auth', 'request-1')
            peer = self.service.connect()
            self.addCleanup(peer.close)
            api.return_value.client.chat_update.side_effect = None
            api.return_value.client.chat_update.return_value = {'ok': True, 'channel': 'CSYNTHETIC', 'ts': '100.001'}
            statuses = InteractiveActions(self.service).confirm_pending(peer, 'fixture')
            self.assertEqual(statuses, [{'status': 'confirmed'}])
            calls = api.return_value.client.chat_update.call_args_list
            self.assertEqual(calls[0].kwargs, calls[1].kwargs)
            self.assertEqual(self.actions.receive(peer, 'fixture', 'auth', 'request-1'), original)

    def test_cli_wires_post_ack_confirmation_without_losing_socket_event_callbacks(self):
        from types import SimpleNamespace
        from slack_mirror.cli.main import cmd_serve_socket_mode
        self.send()
        payload = self.payload()
        def socket_driver(**callbacks):
            self.assertIn('on_event', callbacks)
            self.assertTrue(callbacks['on_interactive']('cli-confirmed', payload))
            callbacks['after_interactive'](payload)
        with patch('slack_mirror.service.server.run_socket_mode', side_effect=socket_driver), patch('slack_mirror.service.interactive.SlackApiClient') as api:
            api.return_value.client.chat_update.return_value = {'ok': True, 'channel': 'CSYNTHETIC', 'ts': '100.001'}
            self.assertEqual(cmd_serve_socket_mode(SimpleNamespace(config=self.config_path, workspace='fixture')), 0)
            self.assertEqual(api.return_value.client.chat_update.call_count, 1)

if __name__ == '__main__':
    unittest.main()
