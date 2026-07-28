"""Golden V2 real query seed import。"""

from __future__ import annotations

import json

import pytest

from linkrag_eval.golden_v2 import import_query_seeds


def _write_jsonl(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_import_query_seeds_jsonl_filters_and_deduplicates(tmp_path) -> None:
    raw = tmp_path / "raw.jsonl"
    out = tmp_path / "query_seeds.jsonl"
    _write_jsonl(
        raw,
        [
            {"qid": "001", "query": "  办理 时限 是多久  ", "domain": "policy", "dataset_ids": "1,2"},
            {"qid": "002", "query": "办理 时限 是多久"},
            {"qid": "003", "query": "x"},
            {"qid": "004", "query": "请联系 13800138000"},
            {"qid": "005", "query": "sk-abcdefghijklmnop"},
            {"qid": "006", "query": "会员积分怎么抵扣", "type_hint": "paraphrase"},
        ],
    )

    report = import_query_seeds(
        raw,
        out=out,
        source="support",
        id_field="qid",
        report_out=tmp_path / "report.json",
    )

    assert report.input_rows == 6
    assert report.written == 2
    assert report.skipped_duplicate == 1
    assert report.skipped_short == 1
    assert report.skipped_pii == 1
    assert report.skipped_secret == 1
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["seed_id"] == "support-001"
    assert rows[0]["query"] == "办理 时限 是多久"
    assert rows[0]["dataset_ids"] == [1, 2]
    assert rows[1]["type_hint"] == "paraphrase"
    assert (tmp_path / "report.json").exists()


def test_import_query_seeds_tsv(tmp_path) -> None:
    raw = tmp_path / "raw.tsv"
    raw.write_text(
        "qid\tquestion\tdomain\n"
        "a1\t售后政策在哪里看\tproduct\n",
        encoding="utf-8",
    )

    report = import_query_seeds(
        raw,
        out=tmp_path / "query_seeds.jsonl",
        source="log",
        input_format="tsv",
        query_field="question",
        id_field="qid",
    )

    assert report.written == 1
    row = json.loads((tmp_path / "query_seeds.jsonl").read_text(encoding="utf-8"))
    assert row["seed_id"] == "log-a1"
    assert row["source"] == "log"
    assert row["domain"] == "product"


def test_import_query_seeds_does_not_duplicate_source_prefix(tmp_path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_jsonl(raw, [{"qid": "spark-realistic-0001", "query": "材料不全要怎么办"}])

    import_query_seeds(
        raw,
        out=tmp_path / "query_seeds.jsonl",
        source="spark_realistic",
        id_field="qid",
    )

    row = json.loads((tmp_path / "query_seeds.jsonl").read_text(encoding="utf-8"))
    assert row["seed_id"] == "spark-realistic-0001"


def test_import_query_seeds_can_allow_pii(tmp_path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_jsonl(raw, [{"query": "手机号 13800138000 怎么改"}])

    report = import_query_seeds(
        raw,
        out=tmp_path / "query_seeds.jsonl",
        source="manual",
        reject_pii=False,
    )

    assert report.written == 1
    assert report.skipped_pii == 0


def test_import_query_seeds_preserves_quality_metadata(tmp_path) -> None:
    raw = tmp_path / "raw.jsonl"
    _write_jsonl(
        raw,
        [
            {
                "query": "材料不全时审批还能继续吗",
                "source_channel": "support",
                "difficulty": "hard",
                "notes": "多约束口语问法",
            }
        ],
    )

    import_query_seeds(raw, out=tmp_path / "query_seeds.jsonl", source="spark_realistic")

    row = json.loads((tmp_path / "query_seeds.jsonl").read_text(encoding="utf-8"))
    assert row["metadata"]["source_channel"] == "support"
    assert row["metadata"]["difficulty"] == "hard"
    assert row["metadata"]["notes"] == "多约束口语问法"


def test_import_query_seeds_rejects_bad_format(tmp_path) -> None:
    raw = tmp_path / "raw.txt"
    raw.write_text("query\n问题\n", encoding="utf-8")

    with pytest.raises(ValueError, match="不支持"):
        import_query_seeds(
            raw,
            out=tmp_path / "query_seeds.jsonl",
            source="manual",
            input_format="xlsx",
        )
