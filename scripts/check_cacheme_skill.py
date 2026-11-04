"""Exercise the real cache-me skill with Codex against disposable synthetic data.

Uses Codex's existing login without reading/copying credentials. The application
data and workspace are temporary; every MCP endpoint override is process-local.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import tomllib
from uuid import UUID, uuid4

from check_codex import Codex
from second_brain.brand import DEFAULT_PORT, MCP_SERVER_KEY

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "docs/skills/cache-me/SKILL.md"
MUTATIONS = {"capture_create", "capture_update", "capture_merge", "capture_set_concepts",
             "capture_retry_concepts", "capture_review_sources", "capture_delete",
             "concept_create", "concept_update", "relation_create", "relation_retract"}


def committed(record):
    return {key: record.get(key) for key in (
        "id", "revision_id", "revision_no", "state_version", "title", "body_markdown",
        "kinds", "visibility", "completion_state", "event_time", "concept_hints")}


class ModelTurnError(RuntimeError):
    def __init__(self, scenario):
        self.scenario = scenario
        super().__init__(f"Model turn {scenario['name']} did not complete: {scenario.get('turn_status', 'interrupted')}")


class SkillProbe(Codex):
    def __init__(self, process):
        super().__init__(process, False)
        self.current = None
        self.pending_turn_messages = []

    async def notification(self, message):
        method = message.get("method")
        if "id" in message and method:
            # Only the disposable server's ordinary tool permission is accepted.
            # A deletion form is always declined, including repeated requests.
            params = message.get("params", {})
            if method == "mcpServer/elicitation/request":
                properties = params.get("requestedSchema", {}).get("properties", {})
                ordinary_permission = not properties and f"{MCP_SERVER_KEY} MCP server to run tool" in params.get("message", "")
                result = {"action": "accept", "content": {}} if ordinary_permission else {"action": "decline"}
                if self.current is not None:
                    self.current["confirmations"].append({"action": result["action"], "deletion": "delete" in properties})
                await self.send({"id": message["id"], "result": result})
            else:
                await self.send({"id": message["id"], "error": {"code": -32601, "message": "Unsupported request in isolated verification"}})
            return
        if self.current is None:
            return
        params = message.get("params", {})
        if params.get("threadId") not in (None, self.current.get("thread_id")):
            return
        if method in ("item/completed", "turn/completed") and not self.current.get("turn_id"):
            self.pending_turn_messages.append(message)
            return
        event_turn = params.get("turnId") or (params.get("turn", {}).get("id") if method == "turn/completed" else None)
        if self.current.get("turn_id") and event_turn not in (None, self.current["turn_id"]):
            return
        if method == "turn/completed":
            self.current["turn_status"] = params["turn"]["status"]
            self.current["completion_turn_id"] = event_turn
            if params["turn"].get("error"):
                error = params["turn"]["error"]
                self.current["turn_error"] = {key: error.get(key) for key in ("message", "codexErrorInfo")}
        if method == "item/completed":
            item = message.get("params", {}).get("item", {})
            kind = item.get("type")
            if kind == "agentMessage":
                self.current["model_messages"].append(item.get("text", ""))
            elif kind == "mcpToolCall":
                call = {key: item.get(key) for key in ("server", "tool", "arguments", "status")}
                result = item.get("result") or {}
                content = result.get("structuredContent")
                if isinstance(content, dict):
                    call["ok"] = content.get("ok")
                self.current["tool_calls"].append(call)
                print(f"{self.current['name']}: {call['tool']} {call['status']}", flush=True)
            elif kind == "commandExecution":
                command = item.get("command", "")
                output = item.get("aggregatedOutput", "")
                if "SKILL.md" in command and ("cache-me" in command or "cache-me" in output):
                    self.current["skill_reads"].append({"command": command, "exit_code": item.get("exitCode"),
                        "body_observed": "## 호출과 범위" in output and "cache-me" in output})

    async def model_turn(self, name, prompt, *, selected=False, thread_id=None):
        scenario = {"name": name, "prompt": prompt, "structured_skill_selected": selected,
                    "skill_reads": [], "tool_calls": [], "model_messages": [], "confirmations": []}
        if thread_id is None:
            thread = await self.call("thread/start", {"cwd": self.workspace, "ephemeral": True,
                "approvalPolicy": "on-request", "sandbox": "read-only",
                "developerInstructions": f"검증에 쓰는 모든 기록은 합성 자료이고 연결된 {MCP_SERVER_KEY} 서버는 격리된 임시 저장소다. "
                    "연결된 MCP 도구와 필요한 스킬 문서 읽기만 사용한다. 인증/설정 파일, 실제 앱 데이터는 읽거나 쓰지 않는다. "
                    "저장·정정 결과에는 실제 반환된 제목·본문·유형·공개 범위·완료 상태를 보여준다."})
            thread_id = thread["thread"]["id"]
        scenario["thread_id"] = thread_id
        self.current = scenario
        try:
            inputs = [{"type": "text", "text": prompt}]
            if selected:
                inputs.append({"type": "skill", "name": "cache-me", "path": str(SKILL)})
            started = await self.call("turn/start", {"threadId": thread_id, "input": inputs})
            scenario["turn_id"] = started["turn"]["id"]
            pending, self.pending_turn_messages = self.pending_turn_messages, []
            for message in pending:
                await self.notification(message)
            while "turn_status" not in scenario:
                line = await asyncio.wait_for(self.process.stdout.readline(), 300)
                if not line:
                    raise RuntimeError("Codex closed during the isolated model turn")
                await self.notification(json.loads(line))
            if scenario["turn_status"] != "completed":
                raise ModelTurnError(scenario)
            return scenario
        finally:
            self.current = None
            self.pending_turn_messages = []

    async def tool(self, thread_id, name, arguments):
        result = await self.call("mcpServer/tool/call", {"threadId": thread_id,
            "server": MCP_SERVER_KEY, "tool": name, "arguments": arguments})
        payload = result.get("structuredContent")
        if not payload:
            for content in result.get("content", []):
                if content.get("type") == "text":
                    payload = json.loads(content["text"])
                    break
        assert payload is not None and payload.get("ok"), f"Isolated {name} failed"
        return payload["data"]


def used(scenario, tool):
    return [call for call in scenario["tool_calls"] if call["tool"] == tool]


def assert_natural_skill_read(scenario):
    assert not scenario["structured_skill_selected"]
    assert any(read["body_observed"] for read in scenario["skill_reads"]), "Natural request did not visibly read the new skill"


def assert_committed_content_shown(scenario, record):
    text = "\n".join(scenario["model_messages"])
    unquoted = "\n".join(line[1:].removeprefix(" ") if line.startswith(">") else line
                         for line in text.split("\n"))
    assert all(value in text or value in unquoted for value in (record["title"], record["body_markdown"])), "Committed title or body was not shown"


async def snapshot_records(codex, control_id):
    page = await codex.tool(control_id, "capture_list", {"limit": 100})
    assert page["next_cursor"] is None, "Boundary fixture exceeded the verification window"
    return {item["id"]: committed(await codex.tool(control_id, "capture_get", {"capture_id": item["id"]}))
            for item in page["items"]}


def assert_boundary_records(scenario, before, after, groups, *, exact_body=None):
    """Check committed storage and write operations, not phrasing in the prompt."""
    created = [value for id, value in after.items() if id not in before]
    scenario["committed"] = created
    writes = [call for call in scenario["tool_calls"] if call["tool"] in MUTATIONS or call["tool"] == "capture_delete_prepare"]
    assert all(call["tool"] == "capture_create" and call["server"] == MCP_SERVER_KEY for call in writes), "Unexpected mutation outside record creation"
    logical_creates = {}
    for call in writes:
        payload = call["arguments"]["input"]
        request_id = str(UUID(payload["request_id"]))
        if request_id in logical_creates:
            assert logical_creates[request_id] == payload, "A request ID was reused with different input"
        else:
            logical_creates[request_id] = payload
    assert len(logical_creates) == len(groups), "Unexpected number of logical record creates"
    payloads, request_ids = list(logical_creates.values()), list(logical_creates)
    assert all(after.get(id) == value for id, value in before.items()), "Existing records changed or disappeared"
    assert len(created) == len(groups), "Committed record count differs from the intended units"
    assert all(record["title"] and record["visibility"] == "private" for record in created)
    for payload in payloads:
        assert any(record["body_markdown"] == payload["body_markdown"] and record["title"] == payload.get("title")
                   for record in created), "A submitted body was not found in committed storage"
    for group in groups:
        matches = [record for record in created if all(term in record["body_markdown"] for term in group["required"])]
        assert len(matches) == 1, "A semantic unit was omitted, duplicated, or split"
        record = matches[0]
        searchable = json.dumps({key: record[key] for key in ("title", "body_markdown", "concept_hints")}, ensure_ascii=False)
        assert not any(term in searchable for term in group.get("forbidden", [])), "Unrelated context leaked into a record"
        assert_committed_content_shown(scenario, record)
    if exact_body is not None:
        assert len(created) == 1 and created[0]["body_markdown"] == exact_body, "The supplied document was rewritten or split"
    scenario["request_ids"] = request_ids


async def run_boundary_scenarios(codex, control_id, summary, save, nonce):
    async def context_turn(name, prompt, thread_id=None):
        before = await snapshot_records(codex, control_id)
        scenario = await codex.model_turn(name, prompt, thread_id=thread_id)
        summary["scenarios"].append(scenario)
        assert not any(call["tool"] in MUTATIONS or call["tool"] == "capture_delete_prepare"
                       for call in scenario["tool_calls"]), "Context-only turn changed records"
        assert await snapshot_records(codex, control_id) == before
        scenario["passed"] = True
        save()
        return scenario["thread_id"]

    async def save_turn(name, prompt, groups, *, thread_id=None, exact_body=None):
        before = await snapshot_records(codex, control_id)
        scenario = await codex.model_turn(name, prompt, thread_id=thread_id)
        summary["scenarios"].append(scenario)
        assert any(read["body_observed"] for turn in summary["scenarios"]
                   if turn["thread_id"] == scenario["thread_id"] for read in turn["skill_reads"]), "Natural request did not visibly read the new skill in this thread"
        assert_boundary_records(scenario, before, await snapshot_records(codex, control_id), groups, exact_body=exact_body)
        scenario["passed"] = True
        save()

    for scope in ("recent", "all"):
        project_a, project_b = f"별무리-{nonce}-{scope}", f"등대-{nonce}-{scope}"
        thread_id = await context_turn(f"boundary_{scope}_first_topic",
            f"합성 사례를 이야기할게. {project_a} 프로젝트의 문서 사이트는 정적 HTML로 만들기로 했어. "
            "서버 없이 배포할 수 있다는 이유야. 아직 저장하지 말고 내용만 확인해줘.")
        if scope == "recent":
            await save_turn("boundary_recent_initial_save",
                "cache-me, 이 내용을 비공개로 기억해줘.",
                [{"required": [project_a, "HTML"], "forbidden": [project_b, "토요일"]}], thread_id=thread_id)
        await context_turn(f"boundary_{scope}_topic_change",
            f"이제 다른 이야기를 할게. {project_b} 프로젝트의 독서 모임은 격주 토요일에 열기로 했어. "
            "참여자들이 책을 끝낼 시간을 확보하려는 결정이야. 아직 저장하지 말고 확인만 해줘.", thread_id)
        if scope == "recent":
            prompt = "cache-me, 방금 이야기한 내용을 비공개로 기억해줘."
            groups = [{"required": [project_b, "토요일"], "forbidden": [project_a, "HTML"]}]
        else:
            prompt = "cache-me, 이 대화에서 지금까지 이야기한 내용을 모두 비공개로 기억해줘."
            groups = [{"required": [project_a, "HTML"], "forbidden": [project_b, "토요일"]},
                      {"required": [project_b, "토요일"], "forbidden": [project_a, "HTML"]}]
        await save_turn(f"boundary_{scope}_save", prompt, groups, thread_id=thread_id)

    project = f"종이문-{nonce}"
    await save_turn("boundary_related_decision",
        f"합성 사례야. {project} 앱의 로컬 저장소는 SQLite로 결정했어. 오프라인에서도 기록을 읽어야 하기 때문이야. "
        "PostgreSQL도 검토했지만 별도 서버 운영이 필요해 이번에는 선택하지 않았어. "
        "cache-me, 이 결정과 이유를 비공개로 기억해줘.",
        [{"required": [project, "SQLite", "오프라인", "PostgreSQL"]}])

    document = (f"# 합성 운영 메모 {nonce}\n\n"
                "## 문서 사이트\n정적 HTML로 배포한다.\n\n"
                "## 독서 모임\n격주 토요일에 만난다.")
    await save_turn("boundary_original_document",
        "cache-me, 아래 문서를 원문 그대로 비공개로 저장해줘.\n\n" + document,
        [{"required": [nonce, "HTML", "토요일"]}], exact_body=document)


async def run(args):
    import httpx
    from second_brain.codex_integration import server_config

    summary = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
        "client": "actual Codex app-server and existing account model", "isolated_storage": True,
        "installation_scope": "existing_user_installation" if args.global_only else "temporary_repo_skill",
        "scenario_scope": "boundaries" if args.boundaries_only else "installed" if args.global_only else "full",
        "actual_user_records_modified": False, "credentials_read_or_copied_by_harness": False,
        "skill_sha256": hashlib.sha256(SKILL.read_bytes()).hexdigest(), "scenarios": [],
        "limits": ["Model selection is probabilistic; boundary cases reuse the recorded thread IDs while other cases use independent sessions.",
                   "Partial-failure recovery is specified by the skill but not injected into these live scenarios.",
                   "Desktop skill-picker rendering and human deletion confirmation are not tested.",
                   "The explicit global case sends $cache-me as plain text; model behavior is checked, but automatic body injection is not captured."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        while True:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            if port != DEFAULT_PORT:
                break
        with tempfile.TemporaryDirectory(prefix="cache-me-model-check-") as temporary:
            temp = Path(temporary)
            data, workspace = temp / "data", temp / "workspace"
            workspace.mkdir(parents=True)
            if not args.global_only:
                (workspace / ".agents/skills").mkdir(parents=True)
                (workspace / ".agents/skills/cache-me").symlink_to(SKILL.parent, target_is_directory=True)
            env = dict(os.environ, SECOND_BRAIN_DATA_DIR=str(data), SECOND_BRAIN_PORT=str(port))
            env.pop("SECOND_BRAIN_MCP_TOKEN", None)
            # No background enrichment/model auth is needed for exact-title records.
            server_code = "from second_brain.config import Settings; from second_brain.main import create_app; import uvicorn; s=Settings.load(); s.background_jobs=False; uvicorn.run(create_app(s),host='127.0.0.1',port=s.port)"
            with (temp / "server.log").open("w") as server_log, (temp / "codex.log").open("w") as codex_log:
                server = await asyncio.create_subprocess_exec(sys.executable, "-c", server_code,
                    cwd=ROOT, env=env, stdout=server_log, stderr=server_log)
                process = None
                try:
                    async with httpx.AsyncClient() as client:
                        for _ in range(120):
                            try:
                                if (await client.get(f"http://127.0.0.1:{port}/health")).status_code == 200:
                                    break
                            except httpx.HTTPError:
                                pass
                            await asyncio.sleep(.25)
                        else:
                            raise RuntimeError("Isolated application did not become ready")
                    codex_binary = shutil.which("codex")
                    assert codex_binary, "Codex executable is required"
                    actual_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
                    config_path = actual_home / "config.toml"
                    config_bytes = config_path.read_bytes() if config_path.exists() else b""
                    existing = tomllib.loads(config_bytes.decode())
                    command = [codex_binary, "app-server"]
                    for name in existing.get("mcp_servers", {}):
                        if name != MCP_SERVER_KEY:
                            command += ["-c", f"mcp_servers.{name}.enabled=false"]
                    for name in existing.get("plugins", {}):
                        command += ["-c", f"plugins.{name}.enabled=false"]
                    for key, value in server_config(Path(sys.executable), data, port).items():
                        command += ["-c", f"mcp_servers.{MCP_SERVER_KEY}.{key}={json.dumps(value)}"]
                    command += ["-c", "features.apps=false", "-c", "features.plugins=false",
                                "-c", "features.skill_mcp_dependency_install=false",
                                "-c", f"mcp_servers.{MCP_SERVER_KEY}.enabled=true",
                                "-c", f'mcp_servers.{MCP_SERVER_KEY}.default_tools_approval_mode="auto"']
                    process = await asyncio.create_subprocess_exec(*command, cwd=workspace, env=env,
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                        stderr=codex_log, limit=4 * 1024 * 1024)
                    codex = SkillProbe(process)
                    codex.workspace = str(workspace)
                    initialized = await codex.call("initialize", {"clientInfo": {"name": "cache-me-skill-check", "version": "1"},
                        "capabilities": {"experimentalApi": True, "mcpServerOpenaiFormElicitation": True}})
                    summary["runtime"] = initialized.get("userAgent")
                    await codex.send({"method": "initialized", "params": {}})
                    control = await codex.call("thread/start", {"cwd": str(workspace), "ephemeral": True,
                        "approvalPolicy": "on-request", "sandbox": "read-only"})
                    control_id = control["thread"]["id"]
                    summary["model"] = control.get("model")
                    skills = await codex.call("skills/list", {"cwds": [str(workspace)], "forceReload": True})
                    matching = [skill for group in skills.get("data", []) for skill in group.get("skills", [])
                                if skill.get("name") == "cache-me" and skill.get("enabled")]
                    assert matching, "cache-me skill not discovered"
                    if args.global_only:
                        assert all(skill.get("scope") == "user" for skill in matching), "Global verification found a non-user skill"
                        for skill in matching:
                            assert Path(skill["path"]).read_bytes() == SKILL.read_bytes(), "User installation differs from source"
                    summary["skill_catalog"] = [{key: skill.get(key) for key in ("name", "scope", "enabled", "interface")} for skill in matching]
                    inventory = await codex.call("mcpServerStatus/list", {"threadId": control_id, "detail": "toolsAndAuthOnly"})
                    summary["mcp_inventory"] = [{"name": entry.get("name"), "status": entry.get("runtimeStatus"),
                        "tool_count": len(entry.get("tools", {}))} for entry in inventory.get("data", [])]
                    active_servers = [entry.get("name") for entry in inventory.get("data", [])
                                      if entry.get("runtimeStatus") != "disabled" and entry.get("tools")]
                    assert active_servers == [MCP_SERVER_KEY], "Unexpected MCP servers in isolated model session"
                    isolated = next(entry for entry in inventory["data"] if entry.get("name") == MCP_SERVER_KEY)
                    assert isolated.get("httpOrigin") == f"http://127.0.0.1:{port}", "MCP endpoint is not the isolated application"
                    summary["active_mcp_servers"] = active_servers
                    save()
                    assert (await codex.tool(control_id, "capture_list", {"limit": 100}))["items"] == []
                    nonce = uuid4().hex[:8]
                    if args.boundaries_only:
                        await run_boundary_scenarios(codex, control_id, summary, save, nonce)
                        assert (config_path.read_bytes() if config_path.exists() else b"") == config_bytes, "Existing Codex configuration changed"
                        summary["existing_config_unchanged"] = True
                        summary["status"] = "passed"
                        return
                    memo_title = f"[cache-me 검증 {nonce}] 회의 메모"
                    memo_body = "파란 노트는 책상 오른쪽 서랍에 두었다. 이 문장은 격리 검증용 합성 메모다."
                    plan_title = f"[cache-me 검증 {nonce}] 물주기 계획"
                    plan_body = "가상의 베란다 화분에 물을 준다. 아직 완료하지 않은 격리 검증용 계획이다."

                    async def find_exact(title):
                        page = await codex.tool(control_id, "capture_list", {"query": title, "limit": 100})
                        matches = [item for item in page["items"] if item["title"] == title]
                        assert len(matches) == 1, "Expected exactly one synthetic title"
                        return await codex.tool(control_id, "capture_get", {"capture_id": matches[0]["id"]})

                    if args.global_only:
                        scenario = await codex.model_turn("global_explicit_save", f"$cache-me 제목은 '{memo_title}', 본문은 '{memo_body}'로 그대로 저장해줘. 단순 메모이고 공개 범위는 private으로 해줘.")
                        summary["scenarios"].append(scenario)
                        assert not scenario["structured_skill_selected"]
                        scenario["invocation"] = "plain_text_dollar_token"
                        scenario["automatic_skill_body_injection"] = "not_captured"
                        assert len(used(scenario, "capture_create")) == 1
                        memo = await find_exact(memo_title)
                        assert memo["body_markdown"] == memo_body and memo["visibility"] == "private"
                        assert memo["kinds"] == [] and memo["completion_state"] is None
                        assert_committed_content_shown(scenario, memo)
                        scenario["committed"] = committed(memo)
                        scenario["passed"] = True
                        assert (config_path.read_bytes() if config_path.exists() else b"") == config_bytes, "Existing Codex configuration changed"
                        summary["existing_config_unchanged"] = True
                        summary["status"] = "passed"
                        return

                    scenario = await codex.model_turn("selected_save", f"제목은 '{memo_title}', 본문은 '{memo_body}'로 그대로 저장해줘. 단순 메모이고 공개 범위는 private으로 해줘.", selected=True)
                    summary["scenarios"].append(scenario)
                    assert len(used(scenario, "capture_create")) == 1
                    memo = await find_exact(memo_title)
                    assert memo["body_markdown"] == memo_body and memo["visibility"] == "private"
                    assert memo["kinds"] == [] and memo["completion_state"] is None
                    assert_committed_content_shown(scenario, memo)
                    scenario["committed"] = committed(memo)
                    scenario["passed"] = True
                    save()

                    scenario = await codex.model_turn("natural_save", f"cache-me, 제목은 '{plan_title}', 본문은 '{plan_body}'로 그대로 저장해줘. 계획 유형이고 비공개, 미완료로 해줘.")
                    summary["scenarios"].append(scenario)
                    assert_natural_skill_read(scenario)
                    assert len(used(scenario, "capture_create")) == 1
                    plan = await find_exact(plan_title)
                    assert plan["body_markdown"] == plan_body and plan["visibility"] == "private"
                    assert plan["completion_state"] == "incomplete" and plan["kinds"] == ["idea"]
                    assert_committed_content_shown(scenario, plan)
                    scenario["committed"] = committed(plan)
                    scenario["passed"] = True
                    save()

                    scenario = await codex.model_turn("natural_retrieve_sources", f"cache-me, 정확한 제목이 '{memo_title}'인 기록을 찾아서 저장된 본문과 정확한 출처 버전을 확인해 보여줘.")
                    summary["scenarios"].append(scenario)
                    assert_natural_skill_read(scenario)
                    assert used(scenario, "capture_list") and used(scenario, "source_get")
                    assert not any(call["tool"] in MUTATIONS for call in scenario["tool_calls"])
                    for call in used(scenario, "source_get"):
                        source = call["arguments"]["source"]
                        assert source["capture_id"] == memo["id"] and source["revision_id"] == memo["revision_id"]
                    assert memo_body in "\n".join(scenario["model_messages"])
                    scenario["passed"] = True
                    save()

                    scenario = await codex.model_turn("natural_complete", f"cache-me, 제목이 '{plan_title}'인 계획을 완료로 바꿔줘.")
                    summary["scenarios"].append(scenario)
                    assert_natural_skill_read(scenario)
                    updates = used(scenario, "capture_update")
                    assert used(scenario, "capture_get") and len(updates) == 1
                    update = updates[0]["arguments"]["input"]
                    assert update["changes"] == {"completion_state": "completed"}
                    assert update["expected_revision_id"] == plan["revision_id"] and update["expected_state_version"] == plan["state_version"]
                    completed = await find_exact(plan_title)
                    assert completed["completion_state"] == "completed"
                    for key in ("title", "body_markdown", "kinds", "visibility", "event_time", "concept_hints"):
                        assert completed[key] == plan[key], f"Completion unexpectedly changed {key}"
                    assert_committed_content_shown(scenario, completed)
                    scenario["committed"] = committed(completed)
                    scenario["passed"] = True
                    save()

                    for name, prompt in [("name_only", "cache-me"), ("naming_question", "cache-me라는 이름은 어떤 느낌이야?")]:
                        scenario = await codex.model_turn(name, prompt)
                        summary["scenarios"].append(scenario)
                        assert not any(call["tool"] in MUTATIONS for call in scenario["tool_calls"])
                        records = await codex.tool(control_id, "capture_list", {"limit": 100})
                        assert {item["id"] for item in records["items"]} == {memo["id"], plan["id"]}
                        assert committed(await find_exact(memo_title)) == committed(memo)
                        assert committed(await find_exact(plan_title)) == committed(completed)
                        scenario["passed"] = True
                        save()
                    await run_boundary_scenarios(codex, control_id, summary, save, nonce)
                    assert (config_path.read_bytes() if config_path.exists() else b"") == config_bytes, "Existing Codex configuration changed"
                    summary["existing_config_unchanged"] = True
                    summary["status"] = "passed"
                finally:
                    for child in (process, server):
                        if child and child.returncode is None:
                            child.terminate()
                            try:
                                await asyncio.wait_for(child.wait(), 10)
                            except TimeoutError:
                                child.kill()
                                await child.wait()
    except Exception as exc:
        summary["status"] = "failed"
        summary["error"] = {"type": type(exc).__name__, "message": str(exc)}
        if isinstance(exc, ModelTurnError):
            summary["scenarios"].append(exc.scenario)
        raise
    finally:
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
        print(json.dumps({"status": summary["status"], "scenarios": len(summary["scenarios"]), "output": str(args.output)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="실제 Codex 모델의 cache-me 스킬 선택·저장·조회·정정을 임시 저장소에서 검사")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--global-only", action="store_true", help="repo 스킬 없이 실제 사용자 설치본의 일반 텍스트 $cache-me 저장 1회만 검사")
    scope.add_argument("--boundaries-only", action="store_true", help="같은 대화의 주제 전환·저장 범위·기록 단위 4개 사례(9턴)만 검사")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.output is None:
        filename = "cache-me-model-verification.json"
        arguments.output = ROOT / ".local/checks" / filename
    asyncio.run(run(arguments))
