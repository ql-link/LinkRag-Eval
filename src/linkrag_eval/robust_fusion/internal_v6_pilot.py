"""Internal Stress v6 的 DeepSeek 受控合成 Dev 先导。

本模块只生成“待人工复核提案”。它不写 GateA/Blind，不把模型标签当真值，
也不读取或上传项目私有语料。每个 family 独立调用一次，并保存逐调用审计。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from linkrag_eval.judge.eval_llm import EvalChatClient
from linkrag_eval.judge.json_parse import parse_llm_json

SCHEMA_VERSION = "ROBUST-FUSION-INTERNAL-V6-SYNTHETIC-FAMILY-2026-08-29-v1"
RUN_RECORD = "ROBUST-FUSION-INTERNAL-V6-DEEPSEEK-PILOT-2026-08-29-v2"
BATCH_ID = "RF-V6D-20260829-PILOT-V2"
SCIENTIFIC_PROTOCOL = "ROBUST-FUSION-RESEARCH-2026-08-29-v21"
ENGINEERING_PROTOCOL = "ROBUST-FUSION-ENGINEERING-2026-08-29-v12"
INTERNAL_PROTOCOL = "ROBUST-FUSION-INTERNAL-STRESS-2026-08-29-v8"
HANDBOOK_VERSION = "ROBUST-FUSION-ANNOTATION-HANDBOOK-2026-08-29-v2"

FROZEN_FAMILY_COUNT = 30
FROZEN_TEMPERATURE = 0.7
FROZEN_MAX_TOKENS = 8192
FROZEN_TIMEOUT_SECONDS = 90.0
FROZEN_CONCURRENCY = 6
FROZEN_MAX_RETRIES = 6

CONFLICT_QUOTA = {
    "version_or_time": 8,
    "numeric": 8,
    "negation_or_direction": 7,
    "applicability_or_condition": 7,
}

PRICE_SNAPSHOT = {
    "price_snapshot_id": "DEEPSEEK-V4-FLASH-2026-08-17-RMB-v1",
    "source_url": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
    "effective_from": "2026-08-17",
    "currency": "CNY",
    "unit": "per_million_tokens",
    "timezone": "Asia/Shanghai",
    "peak_windows": ["09:00-12:00", "14:00-18:00"],
    "prices": {
        "off_peak": {"cache_hit_input": 0.05, "cache_miss_input": 1.5, "output": 4.5},
        "peak": {"cache_hit_input": 0.10, "cache_miss_input": 3.0, "output": 9.0},
    },
}


@dataclass(frozen=True)
class FamilySpec:
    ordinal: int
    primary_conflict_type: str
    fictional_domain: str
    topic_seed: str

    @property
    def call_id(self) -> str:
        return f"RF-V6D-CALL-{self.ordinal:03d}"

    @property
    def generation_id(self) -> str:
        return f"RF-V6D-GEN-{self.ordinal:03d}"

    @property
    def fact_id(self) -> str:
        return f"RF-V6D-FACT-{self.ordinal:03d}"

    @property
    def query_id(self) -> str:
        return f"RF-V6D-Q-{self.ordinal:03d}"

    @property
    def target_document_id(self) -> str:
        return f"RF-V6D-DOC-{self.ordinal:03d}-T"

    @property
    def equivalent_candidate_id(self) -> str:
        return f"RF-V6D-CAND-{self.ordinal:03d}-E"

    @property
    def conflict_candidate_id(self) -> str:
        return f"RF-V6D-CAND-{self.ordinal:03d}-C"

    @property
    def surface_candidate_id(self) -> str:
        return f"RF-V6D-CAND-{self.ordinal:03d}-S"

    @property
    def family_ids(self) -> dict[str, str]:
        return {
            "query_family_id": f"RF-V6D-QF-{self.ordinal:03d}",
            "document_family_id": f"RF-V6D-DF-{self.ordinal:03d}",
            "version_family_id": f"RF-V6D-VF-{self.ordinal:03d}",
            "counterfactual_template_family_id": f"RF-V6D-CF-{self.ordinal:03d}",
        }


_TOPIC_SEEDS = [
    ("云岬市公共服务局", "虚构公共服务项目的生效日期"),
    ("星澜港交通署", "虚构航线的启用月份"),
    ("青屿学院教务处", "虚构课程规则的实施学期"),
    ("霁川园区管理会", "虚构通行证的有效截止日"),
    ("沐风医疗中心", "虚构预约制度的版本年份"),
    ("栖霞文保馆", "虚构开放时段的调整日期"),
    ("澄湾能源站", "虚构设备标准的适用版本"),
    ("曜石社区中心", "虚构补助方案的起始季度"),
    ("鹭原水务所", "虚构家庭用水额度"),
    ("松鹤物流园", "虚构包裹重量上限"),
    ("海镜图书馆", "虚构借阅天数"),
    ("岚谷农技站", "虚构补贴比例"),
    ("银杏康复院", "虚构训练频次"),
    ("砚池数据中心", "虚构备份保留周期"),
    ("北辰渡运处", "虚构渡船载客数量"),
    ("蒲月展览馆", "虚构团体预约人数门槛"),
    ("知雨实验学校", "虚构课程是否允许旁听"),
    ("远汀生态站", "虚构区域是否开放采样"),
    ("鹤望应急中心", "虚构设备是否支持离线模式"),
    ("长风体育馆", "虚构比赛期间是否允许入场"),
    ("镜湖档案馆", "虚构材料是否必须提交原件"),
    ("山岚公交处", "虚构线路运行方向"),
    ("白榆人才中心", "虚构申请人群资格"),
    ("青禾保险社", "虚构理赔触发条件"),
    ("流光设备厂", "虚构型号适配范围"),
    ("临川考试院", "虚构免试条件"),
    ("竹影物业站", "虚构住户停车适用区域"),
    ("南泽科研基地", "虚构样品入库温度条件"),
    ("沧浪文化宫", "虚构儿童票适用年龄"),
    ("朝露健康站", "虚构服务对象的阶段条件"),
]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_family_specs() -> list[FamilySpec]:
    conflict_types: list[str] = []
    for conflict_type, count in CONFLICT_QUOTA.items():
        conflict_types.extend([conflict_type] * count)
    if len(_TOPIC_SEEDS) != FROZEN_FAMILY_COUNT or len(conflict_types) != FROZEN_FAMILY_COUNT:
        raise RuntimeError("Internal v6 冻结 family 数或配额配置损坏")
    specs = [
        FamilySpec(index, conflict_types[index - 1], domain, topic)
        for index, (domain, topic) in enumerate(_TOPIC_SEEDS, start=1)
    ]
    assert Counter(spec.primary_conflict_type for spec in specs) == Counter(CONFLICT_QUOTA)
    return specs


SYSTEM_PROMPT = """你是科研数据构造助手。请只构造完全虚构、自包含的中文微型事实世界，严禁引用、改写或声称核验任何真实人物、机构、政策、疾病处置或现实事件。你只提出待人工审核的数据，不是真值裁判。

输出必须是一个合法 JSON 对象：不要 Markdown 代码围栏、不要前后说明、不要注释。所有文本都必须由本次任务原创。严格遵守用户给出的 ID、冲突类型和原子编辑约束，不得增加第二个事实变化。"""


def build_prompt(spec: FamilySpec, *, batch_id: str = BATCH_ID) -> str:
    ids = spec.family_ids
    template = {
        "schema_version": SCHEMA_VERSION,
        "generation_id": spec.generation_id,
        "batch_id": batch_id,
        "primary_conflict_type": spec.primary_conflict_type,
        "synthetic_fact": {
            "synthetic_fact_id": spec.fact_id,
            "fictional_domain": spec.fictional_domain,
            "entity_name": "自拟但必须属于上述虚构域",
            "answer_slot": "简短事实槽名称",
            "target_answer": "一个连续、可逐字替换的正确答案片段",
            "canonical_fact_statement": "唯一目标事实的完整陈述",
        },
        "query": {"query_id": spec.query_id, "text": "自然中文问题", "origin": "synthetic"},
        "target_evidence": {
            "document_id": spec.target_document_id,
            "text": "包含目标答案且自身完整的目标段落",
            "verbatim_anchor": "目标段落中只出现一次且含目标答案的逐字片段",
            "origin": "synthetic",
        },
        "equivalent_candidate": {
            "candidate_id": spec.equivalent_candidate_id,
            "text": "不同措辞但含同一 target_answer、可替代目标证据的段落",
            "relation_proposal": "equivalent",
            "equivalence_rationale": "为何实体、事实槽、时间和条件均相容",
            "origin": "synthetic",
        },
        "conflict_candidate": {
            "candidate_id": spec.conflict_candidate_id,
            "text": "必须等于 target_evidence.text 只替换一次 atomic_edit.before 后的结果",
            "relation_proposal": "factual_conflict",
            "conflict_type_proposal": spec.primary_conflict_type,
            "atomic_edit": {
                "before": "必须与 synthetic_fact.target_answer 完全相同",
                "after": "一个互不相容的新值或新条件，且不得包含 before",
            },
            "conflict_rationale": "指出唯一发生变化的事实槽",
            "origin": "synthetic",
        },
        "surface_control_candidate": {
            "candidate_id": spec.surface_candidate_id,
            "text": "同主题且词面相似，但谈论另一实体或另一事实槽，不与目标事实冲突",
            "relation_proposal": "other_incorrect",
            "non_conflict_rationale": "为何只是主题相似而不是同槽冲突",
            "same_topic_terms": ["至少两个确实出现在该段落中的词", "第二个词"],
            "origin": "synthetic",
        },
        "family_ids": ids,
        "uncertainty_flags": [],
    }
    conflict_guidance = {
        "version_or_time": "唯一变化必须是同一事实槽中的日期、年份、版本或生效时间。",
        "numeric": "唯一变化必须是同一量和同一口径下的数字；单位与条件保持不变。",
        "negation_or_direction": "唯一变化必须使允许/禁止、存在/不存在、增/减或方向发生反转。",
        "applicability_or_condition": "唯一变化必须是答案成立的人群、型号、区域或触发条件。",
    }[spec.primary_conflict_type]
    return (
        "构造一个受控合成 family。\n"
        f"固定虚构域：{spec.fictional_domain}\n"
        f"主题种子：{spec.topic_seed}\n"
        f"固定主冲突类型：{spec.primary_conflict_type}\n"
        f"类型约束：{conflict_guidance}\n\n"
        "硬约束：\n"
        "1. 所有机构、实体、规则和数值均为虚构；不得使用现实知识，也不得要求联网核证。\n"
        "2. synthetic_fact.target_answer 必须是 target_evidence.text 中恰好出现一次的连续片段。\n"
        "3. conflict_candidate.atomic_edit.before 必须逐字等于 target_answer，并在目标段落中恰好出现一次。\n"
        "4. conflict_candidate.text 必须严格等于：只把目标段落中这一次 before 替换成 after；除此之外连标点都不能变化。\n"
        "5. equivalent_candidate 必须包含逐字相同的 target_answer，但使用不同句法或上下文。\n"
        "6. surface control 必须与 Query 主题高度相似，但因实体或事实槽不同而不是事实冲突；same_topic_terms 每个词都须逐字出现。\n"
        "7. 不得给候选添加可靠性、草稿、核验状态等泄露正确侧的元数据。\n"
        "8. uncertainty_flags 只写真正需要人工注意的问题；无则输出空数组。\n"
        "9. 严格复制下面模板中的所有固定 ID 和枚举值。\n\n"
        "输出 JSON 模板（用实际内容替换说明文字）：\n"
        f"{json.dumps(template, ensure_ascii=False, indent=2)}"
    )


def _mapping(value: Any, name: str, errors: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{name}:必须为对象")
        return {}
    return value


def _required_string(container: Mapping[str, Any], key: str, path: str, errors: list[str]) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key}:必须为非空字符串")
        return ""
    return value


def _expect(value: Any, expected: Any, path: str, errors: list[str]) -> None:
    if value != expected:
        errors.append(f"{path}:应为 {expected!r}，实际为 {value!r}")


def validate_proposal(proposal: Any, spec: FamilySpec, *, batch_id: str = BATCH_ID) -> list[str]:
    """执行闭门结构与逐字原子性校验；不替代人工语义复核。"""
    errors: list[str] = []
    root = _mapping(proposal, "root", errors)
    _expect(root.get("schema_version"), SCHEMA_VERSION, "schema_version", errors)
    _expect(root.get("generation_id"), spec.generation_id, "generation_id", errors)
    _expect(root.get("batch_id"), batch_id, "batch_id", errors)
    _expect(
        root.get("primary_conflict_type"),
        spec.primary_conflict_type,
        "primary_conflict_type",
        errors,
    )

    fact = _mapping(root.get("synthetic_fact"), "synthetic_fact", errors)
    _expect(fact.get("synthetic_fact_id"), spec.fact_id, "synthetic_fact.synthetic_fact_id", errors)
    _expect(
        fact.get("fictional_domain"),
        spec.fictional_domain,
        "synthetic_fact.fictional_domain",
        errors,
    )
    _required_string(fact, "entity_name", "synthetic_fact", errors)
    _required_string(fact, "answer_slot", "synthetic_fact", errors)
    target_answer = _required_string(fact, "target_answer", "synthetic_fact", errors)
    _required_string(fact, "canonical_fact_statement", "synthetic_fact", errors)

    query = _mapping(root.get("query"), "query", errors)
    _expect(query.get("query_id"), spec.query_id, "query.query_id", errors)
    _expect(query.get("origin"), "synthetic", "query.origin", errors)
    _required_string(query, "text", "query", errors)

    target = _mapping(root.get("target_evidence"), "target_evidence", errors)
    _expect(
        target.get("document_id"), spec.target_document_id, "target_evidence.document_id", errors
    )
    _expect(target.get("origin"), "synthetic", "target_evidence.origin", errors)
    target_text = _required_string(target, "text", "target_evidence", errors)
    anchor = _required_string(target, "verbatim_anchor", "target_evidence", errors)

    equivalent = _mapping(root.get("equivalent_candidate"), "equivalent_candidate", errors)
    _expect(
        equivalent.get("candidate_id"),
        spec.equivalent_candidate_id,
        "equivalent_candidate.candidate_id",
        errors,
    )
    _expect(equivalent.get("origin"), "synthetic", "equivalent_candidate.origin", errors)
    _expect(
        equivalent.get("relation_proposal"),
        "equivalent",
        "equivalent_candidate.relation_proposal",
        errors,
    )
    equivalent_text = _required_string(equivalent, "text", "equivalent_candidate", errors)
    _required_string(equivalent, "equivalence_rationale", "equivalent_candidate", errors)

    conflict = _mapping(root.get("conflict_candidate"), "conflict_candidate", errors)
    _expect(
        conflict.get("candidate_id"),
        spec.conflict_candidate_id,
        "conflict_candidate.candidate_id",
        errors,
    )
    _expect(conflict.get("origin"), "synthetic", "conflict_candidate.origin", errors)
    _expect(
        conflict.get("relation_proposal"),
        "factual_conflict",
        "conflict_candidate.relation_proposal",
        errors,
    )
    _expect(
        conflict.get("conflict_type_proposal"),
        spec.primary_conflict_type,
        "conflict_candidate.conflict_type_proposal",
        errors,
    )
    conflict_text = _required_string(conflict, "text", "conflict_candidate", errors)
    _required_string(conflict, "conflict_rationale", "conflict_candidate", errors)
    atomic = _mapping(conflict.get("atomic_edit"), "conflict_candidate.atomic_edit", errors)
    before = _required_string(atomic, "before", "conflict_candidate.atomic_edit", errors)
    after = _required_string(atomic, "after", "conflict_candidate.atomic_edit", errors)

    surface = _mapping(root.get("surface_control_candidate"), "surface_control_candidate", errors)
    _expect(
        surface.get("candidate_id"),
        spec.surface_candidate_id,
        "surface_control_candidate.candidate_id",
        errors,
    )
    _expect(surface.get("origin"), "synthetic", "surface_control_candidate.origin", errors)
    _expect(
        surface.get("relation_proposal"),
        "other_incorrect",
        "surface_control_candidate.relation_proposal",
        errors,
    )
    surface_text = _required_string(surface, "text", "surface_control_candidate", errors)
    _required_string(surface, "non_conflict_rationale", "surface_control_candidate", errors)
    topic_terms = surface.get("same_topic_terms")
    if not isinstance(topic_terms, list) or len(topic_terms) < 2:
        errors.append("surface_control_candidate.same_topic_terms:至少两个词")
    else:
        for index, term in enumerate(topic_terms):
            if not isinstance(term, str) or not term.strip():
                errors.append(
                    f"surface_control_candidate.same_topic_terms[{index}]:必须为非空字符串"
                )
            elif term not in surface_text:
                errors.append(
                    f"surface_control_candidate.same_topic_terms[{index}]:未逐字出现在正文"
                )

    family_ids = _mapping(root.get("family_ids"), "family_ids", errors)
    for key, expected in spec.family_ids.items():
        _expect(family_ids.get(key), expected, f"family_ids.{key}", errors)

    uncertainty_flags = root.get("uncertainty_flags")
    if not isinstance(uncertainty_flags, list) or any(
        not isinstance(item, str) for item in uncertainty_flags
    ):
        errors.append("uncertainty_flags:必须为字符串数组")

    if target_answer and before and target_answer != before:
        errors.append("atomic_edit.before 必须逐字等于 synthetic_fact.target_answer")
    if before and after and (before == after or before in after):
        errors.append("atomic_edit.after 必须与 before 不同且不得包含 before")
    if target_answer and target_text.count(target_answer) != 1:
        errors.append("target_answer 必须在 target_evidence.text 中恰好出现一次")
    if anchor and target_text.count(anchor) != 1:
        errors.append("verbatim_anchor 必须在 target_evidence.text 中恰好出现一次")
    if anchor and target_answer and target_answer not in anchor:
        errors.append("verbatim_anchor 必须包含 target_answer")
    if target_answer and target_answer not in equivalent_text:
        errors.append("equivalent_candidate.text 必须包含逐字 target_answer")
    if before and target_text.count(before) == 1:
        expected_conflict = target_text.replace(before, after, 1)
        if conflict_text != expected_conflict:
            errors.append("conflict_candidate.text 不是目标正文的单次精确原子替换")
    if target_answer and target_answer in conflict_text:
        errors.append("冲突正文仍包含 target_answer")
    nonempty_texts = [
        text for text in (target_text, equivalent_text, conflict_text, surface_text) if text
    ]
    if len(nonempty_texts) != len(set(nonempty_texts)):
        errors.append("目标、等价、冲突和表面对照正文必须互不相同")
    return errors


def price_tier(started_at: datetime) -> str:
    local = started_at.astimezone(ZoneInfo("Asia/Shanghai"))
    clock = local.time().replace(tzinfo=None)
    if time(9, 0) <= clock < time(12, 0) or time(14, 0) <= clock < time(18, 0):
        return "peak"
    return "off_peak"


def extract_usage(raw: Mapping[str, Any]) -> dict[str, Any]:
    usage = raw.get("usage")
    usage = usage if isinstance(usage, Mapping) else {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)
    hit_present = "prompt_cache_hit_tokens" in usage
    miss_present = "prompt_cache_miss_tokens" in usage
    hit_tokens = int(usage.get("prompt_cache_hit_tokens") or 0)
    miss_tokens = int(usage.get("prompt_cache_miss_tokens") or 0)
    inferred = False
    if not hit_present and not miss_present:
        miss_tokens = prompt_tokens
        inferred = True
    elif hit_tokens + miss_tokens < prompt_tokens:
        miss_tokens += prompt_tokens - hit_tokens - miss_tokens
        inferred = True
    return {
        "input_tokens": prompt_tokens,
        "cache_hit_input_tokens": hit_tokens,
        "cache_miss_input_tokens": miss_tokens,
        "output_tokens": output_tokens,
        "cache_partition_inferred": inferred,
    }


def estimate_cost_rmb(usage: Mapping[str, Any], tier: str) -> str:
    prices = PRICE_SNAPSHOT["prices"][tier]
    million = Decimal(1_000_000)
    cost = (
        Decimal(int(usage["cache_hit_input_tokens"])) * Decimal(str(prices["cache_hit_input"]))
        + Decimal(int(usage["cache_miss_input_tokens"])) * Decimal(str(prices["cache_miss_input"]))
        + Decimal(int(usage["output_tokens"])) * Decimal(str(prices["output"]))
    ) / million
    return format(cost.quantize(Decimal("0.000001")), "f")


def utc_now() -> datetime:
    return datetime.now(UTC)


def isoformat(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)


def write_json(path: Path, value: Any) -> None:
    _write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    _write_text(path, "".join(canonical_json(row) + "\n" for row in rows))


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(row) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


def build_execution_plan(
    *,
    endpoint: str,
    model: str,
    specs: list[FamilySpec] | None = None,
    run_record: str = RUN_RECORD,
    batch_id: str = BATCH_ID,
    recovery_of: Mapping[str, Any] | None = None,
    repair_prompt_generation_ids: Iterable[str] = (),
) -> dict[str, Any]:
    selected_specs = specs if specs is not None else build_family_specs()
    return {
        "record_id": run_record,
        "batch_id": batch_id,
        "created_at": isoformat(utc_now()),
        "scope": "internal-v6-dev controlled synthetic construction-yield pilot only",
        "protocol_bindings": {
            "scientific": SCIENTIFIC_PROTOCOL,
            "engineering": ENGINEERING_PROTOCOL,
            "internal_data": INTERNAL_PROTOCOL,
            "annotation_handbook": HANDBOOK_VERSION,
        },
        "gate_a_authorized": False,
        "gate_b_authorized": False,
        "model": model,
        "endpoint_host": urlparse(endpoint).hostname,
        "credentials_recorded": False,
        "private_corpus_uploaded": False,
        "family_count": len(selected_specs),
        "conflict_quota": dict(Counter(spec.primary_conflict_type for spec in selected_specs)),
        "full_pilot_conflict_quota": CONFLICT_QUOTA,
        "temperature": FROZEN_TEMPERATURE,
        "max_output_tokens": FROZEN_MAX_TOKENS,
        "timeout_seconds": FROZEN_TIMEOUT_SECONDS,
        "concurrency": FROZEN_CONCURRENCY,
        "provider_transient_retry_ceiling": FROZEN_MAX_RETRIES,
        "whole_batch_automatic_retry": False,
        "thinking_mode": "disabled",
        "response_format": "json_object",
        "hard_monetary_limit": None,
        "model_output_is_truth": False,
        "recovery_of": dict(recovery_of) if recovery_of is not None else None,
        "repair_prompt_generation_ids": sorted(repair_prompt_generation_ids),
        "families": [asdict(spec) | {"ids": spec.family_ids} for spec in selected_specs],
    }


def validate_frozen_run_config(
    *,
    endpoint: str,
    api_key: str,
    model: str,
    families: int,
    temperature: float,
    max_tokens: int,
    timeout_seconds: float,
    concurrency: int,
    max_retries: int,
    expected_families: int = FROZEN_FAMILY_COUNT,
) -> None:
    expected = {
        "families": (families, expected_families),
        "temperature": (temperature, FROZEN_TEMPERATURE),
        "max_tokens": (max_tokens, FROZEN_MAX_TOKENS),
        "timeout_seconds": (timeout_seconds, FROZEN_TIMEOUT_SECONDS),
        "concurrency": (concurrency, FROZEN_CONCURRENCY),
        "max_retries": (max_retries, FROZEN_MAX_RETRIES),
    }
    drift = [
        f"{name}={actual!r}（冻结值 {frozen!r}）"
        for name, (actual, frozen) in expected.items()
        if actual != frozen
    ]
    if drift:
        raise RuntimeError("运行参数偏离冻结协议：" + "；".join(drift))
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or parsed.hostname != "api.deepseek.com":
        raise RuntimeError("本先导冻结为 https://api.deepseek.com 端点")
    if model != "deepseek-v4-flash":
        raise RuntimeError("本先导冻结模型为 deepseek-v4-flash")
    if not api_key:
        raise RuntimeError("EVAL_JUDGE_API_KEY 未配置")


async def run_pilot(
    *,
    output_dir: Path,
    endpoint: str,
    api_key: str,
    model: str,
    families: int,
    temperature: float,
    max_tokens: int,
    timeout_seconds: float,
    concurrency: int,
    max_retries: int,
    specs: list[FamilySpec] | None = None,
    run_record: str = RUN_RECORD,
    batch_id: str = BATCH_ID,
    recovery_of: Mapping[str, Any] | None = None,
    prompt_suffix_by_generation: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """执行一次冻结批次；目录已存在时拒绝覆盖，失败 family 不自动重跑。"""
    selected_specs = specs if specs is not None else build_family_specs()
    if not selected_specs:
        raise RuntimeError("运行至少需要一个 family")
    if recovery_of is None and selected_specs != build_family_specs():
        raise RuntimeError("正式 v2 首批必须使用冻结的完整 30-family 计划")
    validate_frozen_run_config(
        endpoint=endpoint,
        api_key=api_key,
        model=model,
        families=families,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
        concurrency=concurrency,
        max_retries=max_retries,
        expected_families=len(selected_specs),
    )
    if output_dir.exists():
        raise FileExistsError(f"拒绝覆盖已有运行目录：{output_dir}")
    lowered_parts = {part.lower() for part in output_dir.parts}
    if lowered_parts.intersection({"gate_a", "gatea", "gate_b", "blind"}):
        raise RuntimeError("Internal v6 Dev 先导不得写入 GateA/Blind 路径")

    output_dir.mkdir(parents=True, mode=0o700)
    output_dir.chmod(0o700)
    plan = build_execution_plan(
        endpoint=endpoint,
        model=model,
        specs=selected_specs,
        run_record=run_record,
        batch_id=batch_id,
        recovery_of=recovery_of,
        repair_prompt_generation_ids=(prompt_suffix_by_generation or {}).keys(),
    )
    write_json(output_dir / "execution_plan.json", plan)
    write_json(output_dir / "price_snapshot.json", PRICE_SNAPSHOT)
    _write_text(output_dir / "system_prompt.txt", SYSTEM_PROMPT + "\n")

    requests = []
    for spec in selected_specs:
        prompt = build_prompt(spec, batch_id=batch_id)
        prompt_suffix = (prompt_suffix_by_generation or {}).get(spec.generation_id, "")
        if prompt_suffix:
            prompt = f"{prompt}\n\n{prompt_suffix}"
        requests.append(
            {
                "call_id": spec.call_id,
                "generation_id": spec.generation_id,
                "batch_id": batch_id,
                "primary_conflict_type": spec.primary_conflict_type,
                "system_prompt_sha256": sha256_text(SYSTEM_PROMPT),
                "prompt_sha256": sha256_text(prompt),
                "repair_prompt_suffix_sha256": (
                    sha256_text(prompt_suffix) if prompt_suffix else None
                ),
                "prompt": prompt,
                "request_prepared_at": isoformat(utc_now()),
            }
        )
    # 在任何网络调用前先持久化全部提示词与 hash。
    write_jsonl(output_dir / "call_requests.jsonl", requests)

    raw_path = output_dir / "raw_calls.jsonl"
    usage_path = output_dir / "usage_ledger.jsonl"
    write_jsonl(raw_path, [])
    write_jsonl(usage_path, [])
    request_by_call = {row["call_id"]: row for row in requests}
    lock = asyncio.Lock()
    client = EvalChatClient(
        base_url=endpoint,
        api_key=api_key,
        model=model,
        timeout_s=timeout_seconds,
        max_retries=max_retries,
        concurrency=concurrency,
    )

    async def one(spec: FamilySpec) -> dict[str, Any]:
        request = request_by_call[spec.call_id]
        started = utc_now()
        status = "FAILED"
        response_content = ""
        response_raw: dict[str, Any] = {}
        retry_count: int | None = None
        error_type: str | None = None
        error_message: str | None = None
        try:
            result = await client.generate(
                prompt=request["prompt"],
                system_prompt=SYSTEM_PROMPT,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking=False,
                json_object=True,
            )
            response_content = result.content
            response_raw = result.raw
            retry_count = result.retry_count
            status = "SUCCEEDED"
        except Exception as exc:  # noqa: BLE001 - 审计所有 provider 失败，但不自动吞掉批次状态
            error_type = type(exc).__name__
            error_message = str(exc)
        finished = utc_now()
        usage = extract_usage(response_raw)
        tier = price_tier(started)
        cost = estimate_cost_rmb(usage, tier)
        raw_record = {
            "call_id": spec.call_id,
            "generation_id": spec.generation_id,
            "batch_id": batch_id,
            "primary_conflict_type": spec.primary_conflict_type,
            "model": model,
            "started_at": isoformat(started),
            "finished_at": isoformat(finished),
            "prompt_sha256": request["prompt_sha256"],
            "response_sha256": sha256_text(response_content) if response_content else None,
            "response_content": response_content,
            "provider_response": response_raw,
            "retry_count": retry_count,
            "status": status,
            "error_type": error_type,
            "error_message": error_message,
        }
        usage_record = {
            "call_id": spec.call_id,
            "generation_id": spec.generation_id,
            "batch_id": batch_id,
            "model": model,
            "started_at": isoformat(started),
            "finished_at": isoformat(finished),
            **usage,
            "retry_count": retry_count,
            "status": status,
            "price_snapshot_id": PRICE_SNAPSHOT["price_snapshot_id"],
            "price_tier": tier,
            "estimated_cost_rmb": cost,
        }
        async with lock:
            append_jsonl(raw_path, raw_record)
            append_jsonl(usage_path, usage_record)

        proposal = parse_llm_json(response_content) if response_content else None
        validation_errors = (
            validate_proposal(proposal, spec, batch_id=batch_id)
            if proposal is not None
            else ["response_content:无法解析为 JSON 对象"]
        )
        return {
            "spec": spec,
            "call_status": status,
            "proposal": proposal,
            "validation_errors": validation_errors,
            "usage": usage_record,
        }

    started_batch = utc_now()
    try:
        results = await asyncio.gather(*(one(spec) for spec in selected_specs))
    finally:
        await client.aclose()
    finished_batch = utc_now()
    results.sort(key=lambda item: item["spec"].ordinal)

    proposals: list[dict[str, Any]] = []
    valid_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    for item in results:
        spec = item["spec"]
        proposal_row = {
            "call_id": spec.call_id,
            "generation_id": spec.generation_id,
            "call_status": item["call_status"],
            "structurally_valid": not item["validation_errors"],
            "validation_errors": item["validation_errors"],
            "proposal": item["proposal"],
        }
        proposals.append(proposal_row)
        if item["validation_errors"]:
            rejected_rows.append(proposal_row)
        else:
            valid_rows.append(
                {
                    "call_id": spec.call_id,
                    "generation_id": spec.generation_id,
                    "human_truth_status": "PENDING_DOUBLE_REVIEW",
                    "gate_eligibility": "NOT_ELIGIBLE",
                    "proposal": item["proposal"],
                }
            )
    write_jsonl(output_dir / "family_proposals.jsonl", proposals)
    write_jsonl(output_dir / "structurally_valid_proposals.jsonl", valid_rows)
    write_jsonl(output_dir / "rejected_families.jsonl", rejected_rows)

    usages = [item["usage"] for item in results]
    total_cost = sum(Decimal(item["estimated_cost_rmb"]) for item in usages)
    summary = {
        "record_id": run_record,
        "batch_id": batch_id,
        "started_at": isoformat(started_batch),
        "finished_at": isoformat(finished_batch),
        "requested_family_count": len(selected_specs),
        "successful_call_count": sum(item["call_status"] == "SUCCEEDED" for item in results),
        "failed_call_count": sum(item["call_status"] != "SUCCEEDED" for item in results),
        "structurally_valid_proposal_count": len(valid_rows),
        "rejected_proposal_count": len(rejected_rows),
        "structural_yield": len(valid_rows) / len(selected_specs),
        "conflict_type_counts_valid": dict(
            Counter(row["proposal"]["primary_conflict_type"] for row in valid_rows)
        ),
        "usage": {
            "input_tokens": sum(int(item["input_tokens"]) for item in usages),
            "cache_hit_input_tokens": sum(int(item["cache_hit_input_tokens"]) for item in usages),
            "cache_miss_input_tokens": sum(int(item["cache_miss_input_tokens"]) for item in usages),
            "output_tokens": sum(int(item["output_tokens"]) for item in usages),
            "estimated_cost_rmb": format(total_cost.quantize(Decimal("0.000001")), "f"),
        },
        "human_review_status": "NOT_STARTED",
        "model_output_is_truth": False,
        "gate_a_executed": False,
        "gate_b_executed": False,
        "gate_eligibility": "NOT_ELIGIBLE",
        "status": (
            "COMPLETED_AWAITING_HUMAN_REVIEW"
            if len(valid_rows) == len(selected_specs)
            else "INCOMPLETE_REQUIRES_RECORDED_NEW_BATCH"
        ),
        "whole_batch_automatic_retry_performed": False,
        "thinking_mode": "disabled",
        "response_format": "json_object",
        "recovery_of": dict(recovery_of) if recovery_of is not None else None,
    }
    write_json(output_dir / "preliminary_report.json", summary)
    report_md = (
        "# Internal Stress v6 DeepSeek Dev 先导初步报告\n\n"
        "本报告只统计模型调用与确定性结构校验；模型输出尚未成为人工真值，"
        "也没有运行 Gate A 或 Gate B。\n\n"
        f"- 请求 family：{summary['requested_family_count']}\n"
        f"- 调用成功：{summary['successful_call_count']}\n"
        f"- 结构校验通过：{summary['structurally_valid_proposal_count']}\n"
        f"- 结构拒绝：{summary['rejected_proposal_count']}\n"
        f"- 结构产率：{summary['structural_yield']:.1%}\n"
        f"- 输入 token：{summary['usage']['input_tokens']}\n"
        f"- 输出 token：{summary['usage']['output_tokens']}\n"
        f"- 估算费用：人民币 {summary['usage']['estimated_cost_rmb']} 元\n"
        f"- 状态：`{summary['status']}`\n"
    )
    _write_text(output_dir / "初步报告.md", report_md)

    receipt = {
        **summary,
        "endpoint_host": urlparse(endpoint).hostname,
        "model": model,
        "credentials_recorded": False,
        "private_or_unpublished_corpus_uploaded": False,
        "raw_outputs_preserved": True,
        "price_snapshot_id": PRICE_SNAPSHOT["price_snapshot_id"],
        "output_dir": str(output_dir),
    }
    write_json(output_dir / "execution_receipt.json", receipt)
    manifest_rows = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"}:
            manifest_rows.append(
                {
                    "path": path.relative_to(output_dir).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = {
        "record_id": run_record,
        "batch_id": batch_id,
        "generated_at": isoformat(utc_now()),
        "files": manifest_rows,
    }
    write_json(output_dir / "manifest.json", manifest)
    _write_text(output_dir / "manifest.sha256", sha256_file(output_dir / "manifest.json") + "\n")
    return summary
