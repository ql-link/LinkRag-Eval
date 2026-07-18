from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/prepare_grounded_exact_targets.py"


def _module():
    spec = importlib.util.spec_from_file_location("prepare_grounded_exact_targets", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_expression_requires_grounded_business_value() -> None:
    module = _module()
    text = "版本 v2.4.0 要求等待 24 小时，退款比例为 30%，普通说明编号不作规则。"

    assert set(module.EXACT_RE.findall(text)) == {"v2.4.0", "24 小时", "30%"}


def test_select_targets_balances_datasets_and_scenarios(tmp_path: Path) -> None:
    module = _module()
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text(
        "\n".join(
            [
                '{"dataset_id":1,"doc_id":11,"chunk_id":"c1","content":"等待 24 小时",'
                '"metadata":{"scenario":"s1"}}',
                '{"dataset_id":1,"doc_id":12,"chunk_id":"c2","content":"比例 30%",'
                '"metadata":{"scenario":"s2"}}',
                '{"dataset_id":2,"doc_id":21,"chunk_id":"c3","content":"版本 v2.0",'
                '"metadata":{"scenario":"s1"}}',
                '{"dataset_id":2,"doc_id":22,"chunk_id":"c4","content":"耗时 3 天",'
                '"metadata":{"scenario":"s2"}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = module.select_targets([chunks], per_dataset=2)

    assert len(rows) == 4
    assert [row["dataset_id"] for row in rows].count(1) == 2
    assert [row["dataset_id"] for row in rows].count(2) == 2
