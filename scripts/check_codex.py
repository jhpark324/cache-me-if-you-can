"""Real Codex check on synthetic records; optional model turn uses existing login."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import tomllib
from uuid import uuid4

import httpx

from second_brain.codex_integration import install, server_config

ROOT = Path(__file__).resolve().parents[1]


class Codex:
    def __init__(self, process, human):
        self.process, self.human, self.sequence = process, human, 0
        self.confirmations = []
        self.notifications = []

    async def send(self, value):
        self.process.stdin.write((json.dumps(value) + '\n').encode())
        await self.process.stdin.drain()

    async def notification(self, message):
        if message.get('method') == 'mcpServer/elicitation/request':
            schema = message['params'].get('requestedSchema', {})
            print('ELICITATION_KIND: ' + str(message['params'].get('mode')) + ' fields=' + ','.join(schema.get('properties', {})), flush=True)
            if 'delete' not in schema.get('properties', {}):
                # Harness-only permission to call the isolated synthetic-data tools.
                # The application's separate delete form still requires the handling below.
                if not schema.get('properties') and 'second_brain MCP server to run tool' in message['params'].get('message', ''):
                    await self.send({'id': message['id'], 'result': {'action': 'accept', 'content': {}}})
                else:
                    await self.send({'id': message['id'], 'result': {'action': 'decline'}})
                return
            if self.confirmations and self.human:
                print('HUMAN_CONFIRMATION_REQUIRED: ' + message['params']['message'], flush=True)
                answer = (await asyncio.to_thread(sys.stdin.readline)).strip().lower()
                action = 'accept' if answer == 'accept' else 'decline'
                self.confirmations.append({'action': action, 'source': 'human_stdin'})
            else:
                action = 'decline' if not self.confirmations else 'accept'
                self.confirmations.append({'action': action, 'source': 'automated_test'})
            await self.send({'id': message['id'], 'result': {'action': action,
                **({'content': {'delete': True}} if action == 'accept' else {})}})
        elif 'method' in message:
            self.notifications.append(message['method'])
            if message['method'] == 'item/completed':
                item = message.get('params', {}).get('item', {})
                if item.get('type') == 'agentMessage':
                    print('CODEX_RESULT: ' + item.get('text', '')[:1500], flush=True)
                elif item.get('type') == 'mcpToolCall':
                    print('CODEX_TOOL: ' + str(item.get('tool')) + ' ' + str(item.get('status')) + ' ' + str(item.get('error')), flush=True)

    async def turn(self, thread_id, prompt, skill):
        await self.call('turn/start', {'threadId': thread_id, 'input': [
            {'type': 'text', 'text': prompt}, {'type': 'skill', 'name': 'second-brain', 'path': str(skill)}]})
        while True:
            line = await asyncio.wait_for(self.process.stdout.readline(), 180)
            if not line:
                raise RuntimeError('Codex closed during turn')
            message = json.loads(line)
            await self.notification(message)
            if message.get('method') == 'turn/completed':
                assert message['params']['turn']['status'] == 'completed', 'Codex turn failed'
                return

    async def call(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        await self.send({'id': request_id, 'method': method, 'params': params})
        while True:
            line = await asyncio.wait_for(self.process.stdout.readline(), 150)
            if not line:
                raise RuntimeError('Codex process closed unexpectedly')
            message = json.loads(line)
            if message.get('id') == request_id:
                if 'error' in message:
                    raise RuntimeError(json.dumps(message['error']))
                return message['result']
            else:
                await self.notification(message)


async def run(args):
    if args.port == 0:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            args.port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='second-brain-codex-check-') as temporary:
        temp = Path(temporary)
        data, home = temp / 'data', temp / 'codex'
        env = dict(os.environ, SECOND_BRAIN_DATA_DIR=str(data), SECOND_BRAIN_PORT=str(args.port))
        env.pop('SECOND_BRAIN_MCP_TOKEN', None)
        with (temp / 'server.log').open('w') as log, (temp / 'codex.log').open('w') as codex_log:
            server = await asyncio.create_subprocess_exec(sys.executable, '-m', 'second_brain.main',
                cwd=ROOT, env=env, stdout=log, stderr=log)
            codex_process = None
            try:
                async with httpx.AsyncClient() as client:
                    for _ in range(120):
                        try:
                            response = await client.get(f'http://127.0.0.1:{args.port}/health')
                            if response.status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        await asyncio.sleep(.25)
                    else:
                        raise RuntimeError('Isolated server did not start')
                install(home, ROOT / 'docs/skills/second-brain/SKILL.md',
                        server_config(Path(sys.executable), data, args.port))
                command = [shutil.which('codex'), 'app-server']
                codex_env = dict(env, CODEX_HOME=str(home))
                if args.model_turn:
                    actual_home = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
                    existing = tomllib.loads((actual_home / 'config.toml').read_text())
                    for name in existing.get('mcp_servers', {}):
                        if name != 'second_brain':
                            command += ['-c', f'mcp_servers.{name}.enabled=false']
                    for key, value in server_config(Path(sys.executable), data, args.port).items():
                        command += ['-c', f'mcp_servers.second_brain.{key}={json.dumps(value)}']
                    command += ['-c', 'features.apps=false']
                    command += ['-c', 'mcp_servers.second_brain.default_tools_approval_mode="auto"']
                    codex_env['CODEX_HOME'] = str(actual_home)
                codex_process = await asyncio.create_subprocess_exec(*command,
                    cwd=temp, env=codex_env, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=codex_log, limit=4 * 1024 * 1024)
                codex = Codex(codex_process, args.human)
                await codex.call('initialize', {'clientInfo': {'name': 'second-brain-check', 'version': '1'},
                                                'capabilities': {'experimentalApi': True, 'mcpServerOpenaiFormElicitation': True}})
                await codex.send({'method': 'initialized', 'params': {}})
                thread = await codex.call('thread/start', {'cwd': str(temp), 'ephemeral': True,
                                                          'approvalPolicy': 'on-request', 'sandbox': 'workspace-write'})
                thread_id = thread['thread']['id']
                inventory = await codex.call('mcpServerStatus/list', {'threadId': thread_id,
                    'serverName': 'second_brain', 'detail': 'toolsAndAuthOnly'})
                skills = await codex.call('skills/list', {'cwds': [str(temp)], 'forceReload': True})
                assert any(skill.get('name') == 'second-brain' and skill.get('enabled') is True
                           for group in skills.get('data', []) for skill in group.get('skills', [])), 'Installed skill not discovered'

                async def tool(name, arguments):
                    result = await codex.call('mcpServer/tool/call', {'threadId': thread_id,
                        'server': 'second_brain', 'tool': name, 'arguments': arguments})
                    payload = result.get('structuredContent')
                    if not payload:
                        for content in result.get('content', []):
                            if content.get('type') == 'text':
                                payload = json.loads(content['text'])
                                break
                    assert payload is not None, f'No structured response: {list(result)}'
                    return payload

                created = await tool('capture_create', {'input': {'request_id': str(uuid4()),
                    'title': '[검증용 임시 기록] Codex 연결 확인', 'body_markdown': '이 기록은 격리된 임시 저장소의 연결 검증 자료입니다.',
                    'kinds': ['knowledge']}})
                assert created['ok']
                record = created['data']['capture']
                updated = await tool('capture_update', {'input': {'request_id': str(uuid4()), 'capture_id': record['id'],
                    'expected_revision_id': record['revision_id'], 'expected_state_version': record['state_version'],
                    'changes': {'body_markdown': 'Codex 정정 결과까지 확인한 검증용 임시 기록입니다.'}}})
                assert updated['ok']
                record = updated['data']['capture']
                fetched = await tool('capture_get', {'capture_id': record['id']})
                assert fetched['ok'] and fetched['data']['body_markdown'] == record['body_markdown']
                version = {'capture_id': record['id'], 'expected_revision_id': record['revision_id'],
                           'expected_state_version': record['state_version']}
                preview = await tool('capture_delete_prepare', {'input': version})
                assert preview['ok']
                deletion = dict(version, request_id=str(uuid4()), confirmation_token=preview['data']['confirmation_token'])
                declined = await tool('capture_delete', {'input': deletion})
                assert not declined['ok'] and declined['error']['code'] == 'CONFIRMATION_REQUIRED'
                assert len(codex.confirmations) == 1 and codex.confirmations[0]['action'] == 'decline'
                assert (await tool('capture_get', {'capture_id': record['id']}))['ok']
                if args.model_turn:
                    skill_path = ROOT / 'docs/skills/second-brain/SKILL.md'
                    model_thread = await codex.call('thread/start', {'cwd': str(temp), 'ephemeral': True,
                        'approvalPolicy': 'on-request', 'sandbox': 'workspace-write'})
                    model_thread_id = model_thread['thread']['id']
                    await codex.turn(model_thread_id, '$second-brain 격리된 검증 저장소의 기록 ' + record['id'] +
                        '을 삭제해줘. 도구의 삭제 재확인으로 처리해. 다른 기록은 건드리지 마.', skill_path)
                    read_after = await tool('capture_get', {'capture_id': record['id']})
                    deleted = {'ok': not read_after['ok']}
                else:
                    deleted = await tool('capture_delete', {'input': deletion})
                read_after = await tool('capture_get', {'capture_id': record['id']})
                assert deleted['ok'] == (not read_after['ok'])
                if deleted['ok']:
                    assert read_after['error']['code'] == 'NOT_FOUND'
                if args.model_turn:
                    assert len(codex.confirmations) == 2, 'Codex turn did not expose both elicitations'
                summary = {'client': 'actual Codex app-server', 'isolated_storage': True,
                    'skill_discovered': True, 'mcp_config_contains_credentials': False,
                    'create_update_read': 'passed', 'decline_preserves_record': True,
                    'delete': 'passed' if deleted['ok'] else 'human_declined',
                    'confirmation_events': codex.confirmations,
                    'inventory_server_count': len(inventory.get('data', [])),
                    'desktop_native_form_rendering': 'not_tested'}
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
                print(json.dumps(summary, ensure_ascii=False), flush=True)
            finally:
                for child in (codex_process, server):
                    if child and child.returncode is None:
                        child.terminate()
                        try:
                            await asyncio.wait_for(child.wait(), 10)
                        except TimeoutError:
                            child.kill()
                            await child.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=0, help='기본값은 사용 가능한 임시 포트')
    parser.add_argument('--human', action='store_true', help='삭제 승인에 실제 stdin 응답 사용')
    parser.add_argument('--model-turn', action='store_true', help='실제 Codex 모델 turn에서 스킬과 삭제 재확인 검증')
    parser.add_argument('--output', type=Path, default=Path(tempfile.gettempdir()) / 'second-brain-codex-check.json')
    asyncio.run(run(parser.parse_args()))
