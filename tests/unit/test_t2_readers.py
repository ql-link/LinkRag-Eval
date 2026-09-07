"""原始 T2 入口的身份、原文与四级标签契约；无网络、模型或数据库。"""

from io import StringIO

import pytest

from linkrag_eval.golden.opensource.datasets import (
    iter_t2_collection,
    load_t2ranking,
    parse_t2_collection,
    parse_t2_qrels,
    parse_t2_queries,
    read_t2_qrels,
    read_t2_queries,
)


def test_queries_keep_headerless_consumers_and_original_text():
    body = "001\t  原样问题\t附加内容  \r\n1\t另一问题\n"
    expected = {"001": "  原样问题\t附加内容  ", "1": "另一问题"}
    assert parse_t2_queries(StringIO("qid\ttext\r\n" + body)) == expected
    assert parse_t2_queries(StringIO(body)) == expected
    assert list(parse_t2_queries(StringIO(body))) == ["001", "1"]


def test_duplicate_query_must_not_overwrite_different_text():
    assert parse_t2_queries(["q\t问题\n", "q\t问题\n"]) == {"q": "问题"}
    with pytest.raises(ValueError, match="queries.tsv:3.*重复"):
        parse_t2_queries(
            ["qid\ttext\n", "q\t问题\n", "q\t另一问题\n"], source="queries.tsv"
        )


@pytest.mark.parametrize("line", ["missing-tab\n", "\t问题\n", "q\t \n", "q 1\t问题\n"])
def test_invalid_queries_fail_with_location(line):
    with pytest.raises(ValueError, match="queries.tsv:2"):
        parse_t2_queries(["qid\ttext\n", line], source="queries.tsv")


def test_collection_is_lazy_and_preserves_empty_text():
    def lines():
        yield "pid\ttext\n"
        yield "001\t  原始正文\t更多正文  \r\n"
        yield "2\t\n"
        raise RuntimeError("later lines have not been read")

    passages = parse_t2_collection(lines())
    assert next(passages) == ("001", "  原始正文\t更多正文  ")
    assert next(passages) == ("2", "")
    with pytest.raises(RuntimeError, match="later lines"):
        next(passages)


def test_duplicate_passage_id_fails_even_when_text_matches():
    with pytest.raises(ValueError, match="collection.tsv:3.*重复"):
        list(
            parse_t2_collection(
                ["pid\ttext\n", "p\t正文\n", "p\t正文\n"], source="collection.tsv"
            )
        )


def test_qrels_keep_all_grades_and_distinct_string_ids():
    parsed = parse_t2_qrels(
        StringIO("qid\t-\tpid\trel\n001\t-\t01\t0\n001\t-\t1\t1\n"
                 "001\t-\tp2\t2\n1\t-\tp3\t3\n")
    )
    assert parsed.grades == {("001", "01"): 0, ("001", "1"): 1,
                             ("001", "p2"): 2, ("1", "p3"): 3}
    assert parsed.conflicts == {}
    assert parsed.row_count == 4
    assert parsed.duplicate_rows == 0


def test_conflicts_keep_grade_locations_and_never_reenter_known_grades():
    parsed = parse_t2_qrels(
        StringIO("qid\t-\tpid\trel\nq\t-\tp\t0\nq\t-\tp\t0\n"
                 "q\t-\tp\t3\nq\t-\tp\t2\nq\t-\tp\t3\nq\t-\tz\t1\n"),
        source="qrels.tsv",
    )
    assert parsed.grades == {("q", "z"): 1}
    assert [(item.line_number, item.grade) for item in parsed.conflicts[("q", "p")]] == [
        (2, 0), (4, 3), (5, 2)
    ]
    assert parsed.source == "qrels.tsv"
    assert parsed.row_count == 6
    assert parsed.duplicate_rows == 2


@pytest.mark.parametrize("line", [
    "q\tp\n", "q\t-\tp\t-1\n", "q\t-\tp\t4\n", "q\t-\tp\t1.0\n",
    "q\t-\tp\t2\textra\n", "\t-\tp\t1\n", "q\t-\t\t1\n",
])
def test_invalid_four_level_qrels_fail_with_location(line):
    with pytest.raises(ValueError, match="qrels.tsv:2"):
        parse_t2_qrels(["qid\t-\tpid\trel\n", line], source="qrels.tsv")


def test_retrieval_header_is_not_a_four_level_qrel():
    with pytest.raises(ValueError, match="四列"):
        parse_t2_qrels(StringIO("qid\tpid\nq\tp\n"))


def test_path_wrappers_and_loader_preserve_queries_without_positive_references(tmp_path):
    collection = tmp_path / "collection.tsv"
    queries = tmp_path / "queries.tsv"
    qrels = tmp_path / "qrels.tsv"
    collection.write_text("pid\ttext\np\t 原始段落 \n", encoding="utf-8")
    queries.write_text("qid\ttext\nq0\t仅零级\nq1\t没有判断\nq2\t正例未映射\n", encoding="utf-8")
    qrels.write_text("qid\t-\tpid\trel\nq0\t-\tp\t0\nq2\t-\tmissing\t3\n", encoding="utf-8")
    assert read_t2_queries(queries) == {"q0": "仅零级", "q1": "没有判断", "q2": "正例未映射"}
    assert read_t2_qrels(qrels).grades == {("q0", "p"): 0, ("q2", "missing"): 3}
    assert list(iter_t2_collection(collection)) == [("p", " 原始段落 ")]
    corpus, judgments = load_t2ranking(collection, queries, qrels)
    assert corpus.passages == {"p": " 原始段落 "}
    assert [(j.qid, j.judged) for j in judgments] == [
        ("q0", {"p": 0}), ("q1", {}), ("q2", {"missing": 3})
    ]


@pytest.mark.parametrize("rows, message", [
    ("q\t-\tp\t0\nq\t-\tp\t1\n", "冲突"),
    ("unknown\t-\tp\t1\n", "不在 queries"),
])
def test_legacy_loader_rejects_unrepresentable_judgments(tmp_path, rows, message):
    queries = tmp_path / "queries.tsv"
    qrels = tmp_path / "qrels.tsv"
    queries.write_text("qid\ttext\nq\t问题\n", encoding="utf-8")
    qrels.write_text("qid\t-\tpid\trel\n" + rows, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_t2ranking(tmp_path / "not-loaded.tsv", queries, qrels)
