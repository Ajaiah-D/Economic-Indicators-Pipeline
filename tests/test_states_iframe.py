"""states_view feature-detects st.iframe, so the 1.53 floor keeps working."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "dashboard" / "states_view.py"


def test_states_view_feature_detects_st_iframe():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    guards = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Call)
        and getattr(node.test.func, "id", "") == "hasattr"
        and [getattr(a, "id", getattr(a, "value", None)) for a in node.test.args] == ["st", "iframe"]
    ]
    assert guards, "expected `if hasattr(st, \"iframe\")` in states_view.py"
    body_calls = {ast.unparse(n.func) for stmt in guards[0].body for n in ast.walk(stmt) if isinstance(n, ast.Call)}
    else_calls = {ast.unparse(n.func) for stmt in guards[0].orelse for n in ast.walk(stmt) if isinstance(n, ast.Call)}
    assert "st.iframe" in body_calls
    assert "components.html" in else_calls
