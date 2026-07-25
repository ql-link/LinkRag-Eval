from __future__ import annotations

import json

from linkrag_eval.golden_v2.structured_corpus import build_structured_corpus


def test_builds_multi_chunk_and_exact_scenarios(tmp_path) -> None:
    provenance={
        "source_kind":"business","source_name":"manual","source_record_id":"r1",
        "domain":"release","scenario":"cross_chunk","canonical_query":"发布日期和版本是什么",
    }
    questions=[]
    for scenario in ("cross_chunk","exact_identifier","date","version"):
        questions.append({
            "id":scenario,"query":f"{scenario} 问题","scenario":scenario,
            "answer_ordinals":[0,1] if scenario=="cross_chunk" else [1],
            "provenance":{**provenance,"source_record_id":scenario,"scenario":scenario},
        })
    specs=tmp_path/"specs.jsonl"
    specs.write_text(json.dumps({
        "doc_key":"release-1","domain":"release","source_uri":"internal://manual",
        "source_version":"v2.4.1","sections":[
            {"heading":"日期","content":"发布日期为2026年7月24日。"},
            {"heading":"版本","content":"版本号是v2.4.1，工单编号为REL-2048。"},
        ],"questions":questions,
    },ensure_ascii=False)+"\n")

    report=build_structured_corpus(
        specs,dataset_id=993000,doc_id_base=99300000001,
        chunks_out=tmp_path/"chunks.jsonl",qrels_out=tmp_path/"qrels.jsonl",
    )
    qrels=[json.loads(line) for line in (tmp_path/"qrels.jsonl").read_text().splitlines()]
    assert report.chunks == 2
    assert report.multi_positive_queries == 1
    assert len(qrels[0]["expected_chunk_ids"]) == 2
