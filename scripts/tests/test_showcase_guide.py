"""The public MCP guide should cover the same tools that the server registers."""
import ast
from html.parser import HTMLParser
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ToolInventory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_inventory = False
        self.in_code = False
        self.names = set()

    def handle_starttag(self, tag, attrs):
        if tag == "section" and dict(attrs).get("id") == "tools":
            self.in_inventory = True
        if tag == "code" and self.in_inventory:
            self.in_code = True

    def handle_endtag(self, tag):
        if tag == "code":
            self.in_code = False
        if tag == "section":
            self.in_inventory = False

    def handle_data(self, data):
        if self.in_code and data.isidentifier():
            self.names.add(data)


class ShowcaseGuideTest(unittest.TestCase):
    def test_guide_lists_every_registered_mcp_tool(self):
        module = ast.parse((ROOT / "backend/src/cache_me/mcp_server.py").read_text(encoding="utf-8"))
        registered = {
            node.name for node in ast.walk(module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(decorator, ast.Call) and ast.unparse(decorator.func) == "mcp.tool"
                for decorator in node.decorator_list
            )
        }
        guide = ToolInventory()
        guide.feed((ROOT / "docs/showcase/guide-system.html").read_text(encoding="utf-8"))
        self.assertTrue(registered)
        self.assertEqual(guide.names, registered)
