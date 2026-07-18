"""Golden V2 合成背景语料生成。

输入来自外部模型生成的 spec JSON,本模块只做确定性扩写和标准化输出。
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from linkrag_eval.store.ids import content_hash, eval_chunk_id


@dataclass(frozen=True)
class SynthCorpusReport:
    dataset_id: int
    target_chunks: int
    chunks: int
    domains: list[str]
    doc_id_min: int | None
    doc_id_max: int | None
    chunk_records_path: str
    corpus_blueprints_path: str
    manifest_path: str
    report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        return (
            f"合成背景语料完成: dataset_id={self.dataset_id} chunks={self.chunks}/"
            f"{self.target_chunks} domains={len(self.domains)}"
        )


def synthesize_corpus_from_spec(
    spec_path: str | Path,
    *,
    dataset_id: int,
    target_chunks: int,
    out_dir: str | Path,
    seed: int = 20260709,
    batch_id: str | None = None,
    report_out: str | Path | None = None,
) -> SynthCorpusReport:
    """从 Spark spec 扩写标准 ``chunk_records`` 与 ``corpus_blueprints``。"""

    if target_chunks <= 0:
        raise ValueError("target_chunks 必须大于 0")
    spec = _load_spec(Path(spec_path))
    domains = _normalize_domains(spec)
    if not domains:
        raise ValueError("spec.domains 为空")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    chunk_records_path = out_path / "chunk_records.jsonl"
    blueprints_path = out_path / "corpus_blueprints.jsonl"
    manifest_path = out_path / "synth_manifest.json"
    effective_batch_id = batch_id or f"synth-{dataset_id}-{target_chunks}"
    rng = random.Random(seed)

    chunks: list[dict[str, Any]] = []
    blueprints: list[dict[str, Any]] = []
    for index in range(target_chunks):
        domain = domains[index % len(domains)]
        scenario = _pick(domain["scenarios"], index, rng)
        related_scenario = _pick(domain["scenarios"], index * 11 + 4, rng)
        entity = _pick(domain["entities"], index * 3 + 1, rng)
        related_entity = _pick(domain["entities"], index * 13 + 2, rng)
        constraint = _pick(domain["constraints"], index * 5 + 2, rng)
        related_constraint = _pick(domain["constraints"], index * 17 + 3, rng)
        distractor = _pick(domain["hard_distractors"], index * 7 + 3, rng)
        related_distractor = _pick(domain["hard_distractors"], index * 19 + 1, rng)
        variant = index // len(domains)
        doc_id = dataset_id * 100000 + index + 1
        ordinal = 0
        content = _render_chunk(
            domain=domain["domain"],
            scenario=scenario,
            related_scenario=related_scenario,
            entity=entity,
            related_entity=related_entity,
            constraint=constraint,
            related_constraint=related_constraint,
            distractor=distractor,
            related_distractor=related_distractor,
            variant=variant,
        )
        chunks.append(
            {
                "dataset_id": dataset_id,
                "doc_id": doc_id,
                "ordinal": ordinal,
                "content": content,
                "content_hash": content_hash(content),
                "chunk_id": eval_chunk_id(dataset_id, doc_id, ordinal),
                "metadata": {
                    "generator": "golden_v2_synth_corpus",
                    "generator_batch_id": effective_batch_id,
                    "source_spec": str(spec_path),
                    "domain": domain["domain"],
                    "scenario": scenario,
                    "variant": variant,
                },
            }
        )
        if variant == 0:
            blueprints.append(
                {
                    "blueprint_id": f"synth-bp-{dataset_id}-{len(blueprints) + 1:04d}",
                    "domain": domain["domain"],
                    "body": f"{domain['domain']} 领域背景语料,覆盖 {scenario}、{constraint}、{distractor} 等相似干扰条件。",
                    "metadata": {
                        "generator": "golden_v2_synth_corpus",
                        "generator_batch_id": effective_batch_id,
                    },
                }
            )

    _write_jsonl(chunk_records_path, chunks)
    _write_jsonl(blueprints_path, blueprints)
    manifest = {
        "kind": "golden_v2_synth_corpus",
        "dataset_id": dataset_id,
        "target_chunks": target_chunks,
        "chunks": len(chunks),
        "seed": seed,
        "batch_id": effective_batch_id,
        "source_spec": str(spec_path),
        "artifacts": {
            "chunk_records": str(chunk_records_path),
            "corpus_blueprints": str(blueprints_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    doc_ids = [int(row["doc_id"]) for row in chunks]
    report = SynthCorpusReport(
        dataset_id=dataset_id,
        target_chunks=target_chunks,
        chunks=len(chunks),
        domains=[domain["domain"] for domain in domains],
        doc_id_min=min(doc_ids) if doc_ids else None,
        doc_id_max=max(doc_ids) if doc_ids else None,
        chunk_records_path=str(chunk_records_path),
        corpus_blueprints_path=str(blueprints_path),
        manifest_path=str(manifest_path),
        report_path=str(report_out) if report_out else str(out_path / "synth_report.json"),
    )
    report_path = Path(report.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _load_spec(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} 不是合法 JSON:{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("spec 顶层必须是 object")
    return data


def _normalize_domains(spec: dict[str, Any]) -> list[dict[str, Any]]:
    raw_domains = spec.get("domains")
    if not isinstance(raw_domains, list):
        raise ValueError("spec.domains 必须是数组")
    domains: list[dict[str, Any]] = []
    for index, row in enumerate(raw_domains, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"domains[{index}] 必须是 object")
        domain = str(row.get("domain") or "").strip()
        if not domain:
            raise ValueError(f"domains[{index}].domain 为空")
        normalized = {
            "domain": domain,
            "scenarios": _string_list(row.get("scenarios"), f"domains[{index}].scenarios"),
            "entities": _string_list(row.get("entities"), f"domains[{index}].entities"),
            "constraints": _string_list(row.get("constraints"), f"domains[{index}].constraints"),
            "hard_distractors": _string_list(
                row.get("hard_distractors"), f"domains[{index}].hard_distractors"
            ),
        }
        domains.append(normalized)
    return domains


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} 必须是数组")
    out = [str(item).strip() for item in value if str(item).strip()]
    if len(out) < 2:
        raise ValueError(f"{label} 至少需要 2 条")
    return out


def _pick(items: Sequence[str], offset: int, rng: random.Random) -> str:
    return items[(offset + rng.randrange(len(items))) % len(items)]


def _render_chunk(
    *,
    domain: str,
    scenario: str,
    related_scenario: str,
    entity: str,
    related_entity: str,
    constraint: str,
    related_constraint: str,
    distractor: str,
    related_distractor: str,
    variant: int,
) -> str:
    templates = (
        "{domain}规则说明：处理{scenario}时，应围绕{entity}核对；适用条件为{constraint}。"
        "关联情形{related_scenario}需要另外识别{related_entity}，并遵守{related_constraint}。"
        "常见误解是“{distractor}”或“{related_distractor}”，两者都不能替代上述规则，需要按具体事实判断。",
        "在{domain}场景中，{scenario}涉及{entity}，而{related_scenario}涉及{related_entity}。"
        "前者规则明确要求{constraint}，后者应适用{related_constraint}。"
        "不要将“{distractor}”直接视为处理结论，也不能用“{related_distractor}”混同两个场景。",
        "{scenario}的核心对象是{entity}，属于{domain}的专项处理范围，本条依据是{constraint}。"
        "与之相邻的{related_scenario}应核对{related_entity}并执行{related_constraint}。"
        "“{distractor}”和“{related_distractor}”只是易混淆情况，不应被当作通用规则。",
        "针对{scenario}，{domain}以{entity}作为判断依据，并执行{constraint}。"
        "当问题转为{related_scenario}时，需要改以{related_entity}和{related_constraint}作为边界。"
        "如果出现“{distractor}”或“{related_distractor}”这类描述，必须区分具体情形后再适用规则。",
    )
    return templates[variant % len(templates)].format(
        domain=domain,
        scenario=scenario,
        related_scenario=related_scenario,
        entity=entity,
        related_entity=related_entity,
        constraint=constraint,
        related_constraint=related_constraint,
        distractor=distractor,
        related_distractor=related_distractor,
    )


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
