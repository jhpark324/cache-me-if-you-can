"""Exercise the real HTTP transport, including server-to-client confirmation."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx
import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import ElicitResult


def test_streamable_http_delete_confirmation_roundtrip(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, SECOND_BRAIN_DATA_DIR=str(tmp_path), SECOND_BRAIN_PORT=str(port))
    with (tmp_path / 'server.log').open('w') as log:
        process = subprocess.Popen([sys.executable, '-m', 'second_brain.main'],
                                   env=env, stdout=log, stderr=log)
        try:
            with httpx.Client() as http:
                for _ in range(100):
                    try:
                        if http.get(f'http://127.0.0.1:{port}/health').status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    assert process.poll() is None
                    time.sleep(.1)
                else:
                    raise AssertionError('HTTP server did not start')
            token = json.loads((tmp_path / 'local-access.json').read_text())['mcp_token']

            async def run():
                confirmations = []

                async def confirm(context, params):
                    # Codex 0.164 rejects extra root form-schema fields before rendering.
                    assert set(params.requested_schema) <= {'$schema', 'type', 'properties', 'required'}
                    assert params.requested_schema['properties']['delete']['type'] == 'boolean'
                    confirmations.append(params.message)
                    return ElicitResult(action='decline') if len(confirmations) == 1 else ElicitResult(
                        action='accept', content={'delete': True})

                async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + token}) as http:
                    transport = streamable_http_client(f'http://127.0.0.1:{port}/mcp/', http_client=http)
                    async with Client(transport, elicitation_callback=confirm, read_timeout_seconds=15) as client:
                        created = await client.call_tool('capture_create', {'input': {
                            'request_id': str(uuid4()), 'body_markdown': 'HTTP 재확인 테스트'}})
                        capture = created.structured_content['data']['capture']
                        expected = {'capture_id': capture['id'], 'expected_revision_id': capture['revision_id'],
                                    'expected_state_version': capture['state_version']}
                        preview = await client.call_tool('capture_delete_prepare', {'input': expected})
                        payload = dict(expected, request_id=str(uuid4()),
                                       confirmation_token=preview.structured_content['data']['confirmation_token'])
                        declined = await client.call_tool('capture_delete', {'input': payload})
                        assert declined.is_error and len(confirmations) == 1
                        assert not (await client.call_tool('capture_get', {'capture_id': capture['id']})).is_error
                        accepted = await client.call_tool('capture_delete', {'input': payload})
                        assert not accepted.is_error and len(confirmations) == 2
                        replay = await client.call_tool('capture_delete', {'input': payload})
                        assert replay.structured_content['data']['replayed'] and len(confirmations) == 2
                        hidden = await client.call_tool('capture_get', {'capture_id': capture['id']})
                        assert hidden.is_error and hidden.structured_content['error']['code'] == 'NOT_FOUND'
            asyncio.run(run())
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
