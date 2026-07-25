#!/usr/bin/env python3
"""生成构造性真值的多 Chunk/编号/日期/版本号语料与 Tune/Blind qrels。"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from linkrag_eval.golden_v2.structured_corpus import build_structured_corpus


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--dataset-id", type=int, default=993102)
    parser.add_argument("--documents", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260724)
    args = parser.parse_args()
    out = Path(args.out_dir)
    specs: list[dict] = []
    for index in range(args.documents):
        serial = index + 1
        version = f"v{2 + serial % 4}.{serial % 10}.{(serial * 7) % 20}"
        date = f"2026-{1 + serial % 12:02d}-{1 + serial % 27:02d}"
        ticket = f"REL-{24000 + serial:05d}"
        service = f"服务组件-{serial:03d}"
        provenance_base = {
            "source_kind": "synthetic",
            "source_name": "LinkRag-Eval structured constructive corpus",
            "domain": "release_management",
            "generator_model": "deterministic_template_v1",
            "pii_redacted": True,
        }
        questions = [
            {
                "id": f"structured-{serial:03d}-cross",
                "query": f"{service} 的发布版本和生效日期分别是什么？",
                "scenario": "cross_chunk",
                "answer_ordinals": [0, 1],
                "golden_answer": f"版本为 {version}，生效日期为 {date}。",
            },
            {
                "id": f"structured-{serial:03d}-identifier",
                "query": f"{service} 对应的发布工单编号是什么？",
                "scenario": "exact_identifier",
                "answer_ordinals": [0],
                "golden_answer": ticket,
            },
            {
                "id": f"structured-{serial:03d}-date",
                "query": f"工单 {ticket} 从哪一天开始生效？",
                "scenario": "date",
                "answer_ordinals": [1],
                "golden_answer": date,
            },
            {
                "id": f"structured-{serial:03d}-version",
                "query": f"{service} 当前冻结版本号是多少？",
                "scenario": "version",
                "answer_ordinals": [0],
                "golden_answer": version,
            },
        ]
        for question in questions:
            question["provenance"] = {
                **provenance_base,
                "source_record_id": question["id"],
                "scenario": question["scenario"],
                "canonical_query": question["query"],
            }
        specs.append(
            {
                "doc_key": f"release-{serial:03d}",
                "domain": "release_management",
                "source_uri": f"eval://structured/releases/{serial:03d}",
                "source_version": "structured_constructive_v1",
                "sections": [
                    {
                        "heading": "版本与工单",
                        "content": (
                            f"{service} 的当前冻结版本为 {version}。本次发布严格绑定工单 "
                            f"{ticket}，相近编号不得替代。"
                        ),
                    },
                    {
                        "heading": "生效窗口",
                        "content": (
                            f"工单 {ticket} 的正式生效日期为 {date}。日期以本段为准，"
                            "准备、审批与回滚演练日期均不作为生效日。"
                        ),
                    },
                    {
                        "heading": "回滚说明",
                        "content": (
                            f"若 {service} 验收失败，应保留工单 {ticket} 的审计记录，"
                            f"并从 {version} 回滚到上一稳定版本。"
                        ),
                    },
                ],
                "questions": questions,
            }
        )
    specs_path = out / "specs.jsonl"
    chunks_path = out / "chunk_records.jsonl"
    qrels_path = out / "qrels_all.jsonl"
    _write_jsonl(specs_path, specs)
    report = build_structured_corpus(
        specs_path,
        dataset_id=args.dataset_id,
        doc_id_base=args.dataset_id * 100_000,
        chunks_out=chunks_path,
        qrels_out=qrels_path,
        report_out=out / "report.json",
    )
    chunk_rows = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines()]
    (out / "candidate_contents.json").write_text(
        json.dumps({row["chunk_id"]: row["content"] for row in chunk_rows}, ensure_ascii=False),
        encoding="utf-8",
    )
    qrels = [json.loads(line) for line in qrels_path.read_text(encoding="utf-8").splitlines()]
    random.Random(args.seed).shuffle(qrels)
    tune_size = len(qrels) * 3 // 8
    _write_jsonl(out / "tune.jsonl", qrels[:tune_size])
    _write_jsonl(out / "blind.jsonl", qrels[tune_size:])
    manifest = {
        "dataset_id": args.dataset_id,
        "generator": "deterministic_template_v1",
        "seed": args.seed,
        "report": report.to_dict(),
        "tune_queries": tune_size,
        "blind_queries": len(qrels) - tune_size,
        "sha256": {
            path.name: _sha(path)
            for path in (specs_path, chunks_path, qrels_path, out / "tune.jsonl", out / "blind.jsonl")
        },
        "candidate_contents_sha256": _sha(out / "candidate_contents.json"),
    }
    (out / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
