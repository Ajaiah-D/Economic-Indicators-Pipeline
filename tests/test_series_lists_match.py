import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE_OF_TRUTH = "ingestion/fetch_fred.py"
COPIES = [
    "dags/fred_ingestion_dag.py",
    "spark/transform_indicators.py",
    "spark/transform_indicators_local.py",
]


def indicators_literal(relative_path: str) -> dict:
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "INDICATORS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"no top-level INDICATORS in {relative_path}")


@pytest.mark.parametrize("path", COPIES)
def test_every_copy_matches_the_ingestion_list(path):
    assert indicators_literal(path) == indicators_literal(SOURCE_OF_TRUTH)


def test_there_are_nine_national_series():
    assert len(indicators_literal(SOURCE_OF_TRUTH)) == 9
