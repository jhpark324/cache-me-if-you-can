"""Export the registered MCP schemas and an isolated three-call example for the showcase."""
import argparse
from datetime import datetime
import asyncio
import json
from pathlib import Path
from uuid import UUID

from mcp.client import Client

from cache_me.db import Database
from cache_me.mcp_server import create_mcp
from cache_me.records import RecordService


DEST = Path(__file__).resolve().parents[2] / "docs/showcase/contracts"


async def registered_schemas(client):
    definitions, tools = {}, {}
    cursor = None
    while True:
        page = await client.list_tools(cursor=cursor) if cursor else await client.list_tools()
        for tool in page.tools:
            entry = {}
            for label, schema in (("input", tool.input_schema), ("output", tool.output_schema)):
                if schema is None:
                    raise ValueError(f"{tool.name} has no {label} schema")
                entry[label] = {key: value for key, value in schema.items() if key != "$defs"}
                if "$defs" in schema:
                    entry[label + "Definitions"] = sorted(schema["$defs"])
                for name, definition in schema.get("$defs", {}).items():
                    if name in definitions and definitions[name] != definition:
                        raise ValueError(f"Conflicting schema definitions for {name}")
                    definitions[name] = definition
            tools[tool.name] = entry
        cursor = page.next_cursor
        if not cursor:
            return {"definitions": definitions, "tools": tools}


async def example_calls(client):
    calls = []

    async def call(name, arguments):
        response = await client.call_tool(name, arguments)
        if response.is_error or not response.structured_content or not response.structured_content["ok"]:
            raise RuntimeError(f"Unexpected result for {name}: {response.content}")
        calls.append({"name": name, "arguments": arguments, "structuredContent": response.structured_content})
        return response.structured_content["data"]

    first = "UDP는 메시지를 독립적인 데이터그램으로 보낸다."
    captured = await call("capture_create", {"input": {
        "request_id": "60fe77df-7166-4998-a11a-b198d2151609", "title": "UDP는 무엇을 보장할까?",
        "kinds": ["knowledge"], "body_markdown": first + "\n\n도착 순서와 전달 성공을 보장하지 않는다.",
    }})
    reference = {"capture_id": captured["capture"]["id"], "revision_id": captured["capture"]["revision_id"],
                 "body_start": 0, "body_end": len(first)}
    resolved = await call("source_get", {"source": reference})
    assert resolved["text"] == first
    await call("article_create", {"input": {
        "request_id": "52c5e813-3707-4592-9c40-60004c76e07d", "title": "UDP의 전달 단위",
        "summary": "UDP가 메시지를 보내는 단위를 복습합니다.",
        "body_markdown": "UDP는 메시지를 독립적인 데이터그램으로 전달한다. [1](#cite-1)",
        "citations": [{"kind": "record", "source": reference}], "topics": ["전송 계층"],
    }})
    return calls


def canonical_examples(calls):
    """Preserve references across calls while allowing fresh database IDs and timestamps."""
    ids = {}

    def normalize(value, field=None):
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {k: normalize(v, k) for k, v in sorted(value.items())}
        if field in ("created_at", "updated_at", "revision_created_at") and isinstance(value, str):
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return "<timestamp>"
        if isinstance(value, str) and field != "request_id":
            try:
                UUID(value)
            except ValueError:
                pass
            else:
                return ids.setdefault(value, len(ids) + 1)
        return value

    return normalize(calls)


async def export(check):
    database = Database(":memory:")
    try:
        records = RecordService(database, principal_scope="mcp:local", session_scope="mcp:local", created_via="mcp")
        async with Client(create_mcp(records, None)) as client:
            schemas = await registered_schemas(client)
            examples = await example_calls(client)
    finally:
        database.close()

    for name, data in [("mcp-schemas.json", schemas), ("mcp-examples.json", examples)]:
        file = DEST / name
        if file.is_file():
            previous = json.loads(file.read_text(encoding="utf-8"))
            if name == "mcp-examples.json":
                matches = canonical_examples(previous) == canonical_examples(data)
            else:
                matches = previous == data
            if matches:
                continue
        if check:
            raise SystemExit(f"{file.name} differs from the registered server. Run backend/scripts/export_mcp_guide.py.")
        file.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check the snapshots and replay all three example calls")
    asyncio.run(export(parser.parse_args().check))
