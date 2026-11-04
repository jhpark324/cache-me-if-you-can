"""Offline checks of the evaluation harness, without model or backend dependencies."""
import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
with patch.object(sys, "path", [str(ROOT / "scripts"), str(ROOT / "backend/src"), *sys.path]):
    spec = importlib.util.spec_from_file_location("check_cacheme_skill", ROOT / "scripts/check_cacheme_skill.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)


class FakeAppServer:
    """A line-delimited app-server stream exercising the real RPC reader/writer."""

    def __init__(self, *turns):
        self.stdout = asyncio.StreamReader()
        self.stdin = self
        self.requests = []
        self.turns = iter(turns)
        self.thread_count = 0
        self.turn_count = 0

    def emit(self, message):
        self.stdout.feed_data((json.dumps(message) + "\n").encode())

    def write(self, line):
        request = json.loads(line)
        self.requests.append(request)
        if request["method"] == "thread/start":
            self.thread_count += 1
            self.emit({"id": request["id"], "result": {"thread": {"id": f"thread-{self.thread_count}"}}})
            return
        assert request["method"] == "turn/start"
        self.turn_count += 1
        options = next(self.turns, {})
        thread_id = request["params"]["threadId"]
        turn_id = f"turn-{self.turn_count}"
        turn = {"id": turn_id, "items": [], "status": options.get("status", "completed"),
                "error": options.get("error")}
        response = {"id": request["id"], "result": {"turn": {**turn, "status": "inProgress"}}}
        if not options.get("early"):
            self.emit(response)
        if options.get("foreign"):
            for other_thread, other_turn in (("another-thread", turn_id), (thread_id, "previous-turn")):
                self.emit({"method": "item/completed", "params": {"threadId": other_thread,
                    "turnId": other_turn, "item": {"id": "unrelated", "type": "agentMessage", "text": "unrelated"}}})
                self.emit({"method": "turn/completed", "params": {"threadId": other_thread,
                    "turn": {"id": other_turn, "items": [], "status": "failed", "error": None}}})
        self.emit({"method": "item/completed", "params": {"threadId": thread_id, "turnId": turn_id,
            "item": {"id": f"message-{turn_id}", "type": "agentMessage", "text": options.get("text", turn_id)}}})
        self.emit({"method": "turn/completed", "params": {"threadId": thread_id, "turn": turn}})
        if options.get("early"):
            self.emit(response)

    async def drain(self):
        pass


class ConversationProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_followup_reuses_thread_and_collects_only_its_own_turn(self):
        process = FakeAppServer({"text": "first"}, {"foreign": True, "text": "second"})
        client = probe.SkillProbe(process)
        client.workspace = "/synthetic"
        first = await client.model_turn("first", "first topic")
        second = await client.model_turn("second", "changed topic", thread_id=first["thread_id"])
        self.assertEqual(process.thread_count, 1)
        starts = [request["params"] for request in process.requests if request["method"] == "turn/start"]
        self.assertEqual([item["threadId"] for item in starts], [first["thread_id"]] * 2)
        self.assertEqual(first["thread_id"], second["thread_id"])
        self.assertNotEqual(first["turn_id"], second["turn_id"])
        self.assertEqual(first["model_messages"], ["first"])
        self.assertEqual(second["model_messages"], ["second"])
        self.assertEqual(second["turn_status"], "completed")
        self.assertIsNone(client.current)

    async def test_early_completion_does_not_hang_and_default_turns_are_independent(self):
        process = FakeAppServer({"early": True, "foreign": True}, {})
        client = probe.SkillProbe(process)
        client.workspace = "/synthetic"
        first = await asyncio.wait_for(client.model_turn("first", "one"), 1)
        second = await client.model_turn("second", "two")
        self.assertEqual(process.thread_count, 2)
        self.assertNotEqual(first["thread_id"], second["thread_id"])
        self.assertEqual(first["completion_turn_id"], first["turn_id"])
        self.assertEqual(first["model_messages"], ["turn-1"])

    async def test_failed_turn_retains_diagnostics_and_does_not_poison_followup(self):
        error = {"message": "Synthetic usage limit", "codexErrorInfo": "usageLimitExceeded"}
        process = FakeAppServer({"status": "failed", "error": error}, {})
        client = probe.SkillProbe(process)
        client.workspace = "/synthetic"
        with self.assertRaises(probe.ModelTurnError) as caught:
            await client.model_turn("failed", "one")
        failure = caught.exception.scenario
        self.assertEqual(failure["turn_error"], error)
        self.assertIsNone(client.current)
        successful = await client.model_turn("recovered", "two", thread_id=failure["thread_id"])
        self.assertEqual(successful["turn_status"], "completed")
        self.assertNotIn("turn_error", successful)
        self.assertEqual(process.thread_count, 1)


class StorageBoundaryTests(unittest.TestCase):
    def fixture(self):
        def record(identifier, title, body):
            return probe.committed({"id": identifier, "title": title, "body_markdown": body,
                "visibility": "private", "revision_id": f"revision-{identifier}", "revision_no": 1,
                "state_version": 1, "kinds": [], "concept_hints": []})
        before = {"existing": record("existing", "Existing", "Keep this prior record.")}
        created = [record("a", "Website", "Project-A uses HTML."), record("b", "Book club", "Project-B meets Saturday.")]
        after = {**before, **{item["id"]: item for item in created}}
        scenario = {"tool_calls": [{"server": probe.MCP_SERVER_KEY, "tool": "capture_create",
            "status": "completed", "ok": True, "arguments": {"input": {"request_id": str(uuid4()),
                "title": item["title"], "body_markdown": item["body_markdown"], "visibility": "private"}}}
            for item in created], "model_messages": ["\n".join(item[key] for item in created for key in ("title", "body_markdown"))]}
        groups = [{"required": ["Project-A", "HTML"], "forbidden": ["Project-B", "Saturday"]},
                  {"required": ["Project-B", "Saturday"], "forbidden": ["Project-A", "HTML"]}]
        return scenario, before, after, groups

    def test_independent_private_records_preserve_existing_content_and_report_commits(self):
        scenario, before, after, groups = self.fixture()
        probe.assert_boundary_records(scenario, before, after, groups)
        self.assertEqual({record["id"] for record in scenario["committed"]}, {"a", "b"})
        self.assertEqual(len(set(scenario["request_ids"])), 2)

    def test_reused_ids_extra_mutations_and_unintended_existing_changes_are_rejected(self):
        for failure in ("same_request_id", "extra_relation", "existing_edit", "existing_delete", "visibility"):
            with self.subTest(failure=failure):
                scenario, before, after, groups = deepcopy(self.fixture())
                if failure == "same_request_id":
                    scenario["tool_calls"][1]["arguments"]["input"]["request_id"] = scenario["tool_calls"][0]["arguments"]["input"]["request_id"]
                elif failure == "extra_relation":
                    scenario["tool_calls"].append({"tool": "relation_create", "server": probe.MCP_SERVER_KEY})
                elif failure == "existing_edit":
                    after["existing"] = {**after["existing"], "state_version": 2}
                elif failure == "existing_delete":
                    del after["existing"]
                else:
                    after["b"]["visibility"] = "public"
                with self.assertRaises(AssertionError):
                    probe.assert_boundary_records(scenario, before, after, groups)

    def test_exact_retry_is_one_create_but_changed_id_or_input_is_rejected(self):
        scenario, before, after, groups = self.fixture()
        retry = deepcopy(scenario["tool_calls"][0])
        scenario["tool_calls"].append(retry)
        probe.assert_boundary_records(scenario, before, after, groups)
        self.assertEqual(len(scenario["request_ids"]), 2)
        retry["arguments"]["input"]["request_id"] = str(uuid4())
        with self.assertRaises(AssertionError):
            probe.assert_boundary_records(scenario, before, after, groups)
        retry["arguments"]["input"]["request_id"] = scenario["tool_calls"][0]["arguments"]["input"]["request_id"]
        retry["arguments"]["input"]["visibility"] = "public"
        with self.assertRaises(AssertionError):
            probe.assert_boundary_records(scenario, before, after, groups)

    def test_missing_or_combined_topics_and_cross_topic_metadata_are_rejected(self):
        for failure in ("omitted", "combined", "title", "concept_hints"):
            with self.subTest(failure=failure):
                scenario, before, after, groups = self.fixture()
                if failure == "omitted":
                    del after["b"]
                elif failure == "combined":
                    after["a"]["body_markdown"] += " Project-B meets Saturday."
                    scenario["tool_calls"][0]["arguments"]["input"]["body_markdown"] = after["a"]["body_markdown"]
                elif failure == "title":
                    after["a"]["title"] += " and Project-B"
                    scenario["tool_calls"][0]["arguments"]["input"]["title"] = after["a"]["title"]
                else:
                    after["a"]["concept_hints"] = ["Project-B"]
                scenario["model_messages"] = ["\n".join(item[key] for item in after.values() for key in ("title", "body_markdown"))]
                with self.assertRaises(AssertionError):
                    probe.assert_boundary_records(scenario, before, after, groups)

    def test_verbatim_document_is_one_record_and_rewrite_is_rejected(self):
        scenario, before, after, _ = self.fixture()
        document = "# Operations\n\n## Website\nUse HTML.\n\n## Club\nMeet Saturday."
        del after["b"]
        after["a"]["body_markdown"] = document
        scenario["tool_calls"] = scenario["tool_calls"][:1]
        scenario["tool_calls"][0]["arguments"]["input"]["body_markdown"] = document
        scenario["model_messages"] = [after["a"]["title"] + "\n" + document]
        groups = [{"required": ["HTML", "Saturday"]}]
        probe.assert_boundary_records(scenario, before, after, groups, exact_body=document)
        with self.assertRaises(AssertionError):
            probe.assert_boundary_records(scenario, before, after, groups, exact_body=document + "\n")

    def test_quoted_committed_body_is_shown_but_rewritten_body_is_rejected(self):
        record = {"title": "Synthetic decision", "body_markdown": "Choose SQLite.\n\n> Keep offline access."}
        quoted = "\n".join("> " + line if line else ">" for line in record["body_markdown"].split("\n"))
        scenario = {"model_messages": [record["title"] + "\n\n" + quoted]}
        probe.assert_committed_content_shown(scenario, record)
        scenario["model_messages"] = [scenario["model_messages"][0].replace("offline", "online")]
        with self.assertRaises(AssertionError):
            probe.assert_committed_content_shown(scenario, record)


if __name__ == "__main__":
    unittest.main()
