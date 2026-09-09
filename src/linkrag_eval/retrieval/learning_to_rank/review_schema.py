"""Explicit structured human-review schema; categories describe evidence, never model mechanisms."""
from __future__ import annotations

import html

ANSWER_SCHEMA_VERSION = 2
REASON_SCHEMA_VERSION = "structured_reasons_v1"
# Completeness policy changes independently of the unchanged answer/storage format.
VALIDATION_POLICY_VERSION = "query_ambiguity_abstention_v1"
STORAGE_SUFFIX = "-structured-v2"
REASON_TYPES = {
    "entity": "人物或对象——说的是不是查询要求的人或东西",
    "action_relation": "行为或关系——谁做了什么，什么属于谁",
    "polarity": "肯定或否定——做了／没做、允许／不允许等",
    "time_quantity_comparison": "时间、数量或比较条件——年份、先后、多少、增长或下降等",
    "missing_information": "缺少必要信息——没有交代回答需要的内容",
    "ambiguity_conflict": "表述有歧义或矛盾——存在不同理解，无法确定",
    "other_unclear": "其他／说不清——不强行猜测，请补充具体疑点",
}
PAIR_REASON_CODES = {
    "one_evidence_other_insufficient": "一段提供必要证据，另一段不足",
    "one_meets_other_fails": "一段满足必要条件，另一段明确不满足",
    "both_support": "两段均能支持",
    "both_insufficient": "两段均不足",
    "both_fail": "两段均明确不满足必要条件",
    "evidence_quality_difference": "两段都有相关证据，但完整性或直接程度不同（需补充）",
    "ambiguity_incomparable": "存在歧义或矛盾，无法可靠比较（需补充）",
    "other": "其他（需补充）",
}
CONTRACT = {
    "answer_schema_version": ANSWER_SCHEMA_VERSION, "reason_schema_version": REASON_SCHEMA_VERSION,
    "validation_policy_version": VALIDATION_POLICY_VERSION,
    "reason_types": REASON_TYPES, "pair_reason_codes": PAIR_REASON_CODES,
    "content_types": ["entity", "action_relation", "polarity", "time_quantity_comparison"],
    "evidence_required_for": ["支持所问条件", "明确不满足必要条件"],
    "paragraph_note_required_for": ["无法裁定"],
    "paragraph_note_required_types": ["other_unclear"],
    "insufficient_applicability": "相关但证据不足",
    "pair_note_required_codes": ["evidence_quality_difference", "ambiguity_incomparable", "other"],
    "same_level_pair_codes": ["both_support", "both_insufficient", "both_fail"],
    "asymmetric_pair_codes": ["one_evidence_other_insufficient", "one_meets_other_fails"],
    "reason_types_optional_query_ambiguity": ["yes", "uncertain"],
    "reason_types_optional_applicability": "无法裁定",
}


def structured_missing(answer: dict) -> list[str]:
    """Only required-field conditions; no relevance or mechanism is inferred."""
    missing = []
    for p in answer.get("paragraphs", []):
        side, kinds = p["display_id"], p.get("reason_types") or []
        note = p.get("reason") or ""
        ambiguity_abstention = (
            answer.get("query_ambiguity") in CONTRACT["reason_types_optional_query_ambiguity"]
            and p.get("applicability") == CONTRACT["reason_types_optional_applicability"]
            and bool(note.strip())
        )
        if not kinds and not ambiguity_abstention:
            missing.append(f"{side}.reason_types")
        if p.get("applicability") in CONTRACT["evidence_required_for"] and not p.get("evidence_spans"):
            missing.append(f"{side}.evidence")
        if (p.get("applicability") in CONTRACT["paragraph_note_required_for"]
                or any(t in kinds for t in CONTRACT["paragraph_note_required_types"])) and not note.strip():
            missing.append(f"{side}.specific_uncertainty")
        if (p.get("applicability") == CONTRACT["insufficient_applicability"]
                and not any(t in kinds for t in CONTRACT["content_types"]) and not note.strip()):
            missing.append(f"{side}.missing_information_type_or_note")
    code, note = answer.get("pair_reason_code"), answer.get("pair_reason") or ""
    if not code:
        missing.append("pair_reason_code")
    needs_note = (code in CONTRACT["pair_note_required_codes"]
                  or answer.get("query_ambiguity") in {"yes", "uncertain"}
                  or answer.get("pair_preference") == "undetermined"
                  or (code in CONTRACT["same_level_pair_codes"] and answer.get("pair_preference") in {"X", "Y"})
                  or (code in CONTRACT["asymmetric_pair_codes"] and answer.get("pair_preference") == "tie"))
    if needs_note and not note.strip():
        missing.append("pair_specific_note")
    return missing


def structured_errors(answer: dict) -> list[str]:
    errors = []
    if answer.get("answer_schema_version") != ANSWER_SCHEMA_VERSION:
        errors.append("answer schema version mismatch")
    code = answer.get("pair_reason_code")
    if code is not None and (not isinstance(code, str) or code not in {"", *PAIR_REASON_CODES}):
        errors.append("unknown pair reason code")
    for p in answer.get("paragraphs", []):
        kinds = p.get("reason_types")
        if (not isinstance(kinds, list) or any(not isinstance(v, str) or v not in REASON_TYPES for v in kinds)
                or (isinstance(kinds, list) and all(isinstance(v, str) for v in kinds) and len(set(kinds)) != len(kinds))):
            errors.append(f"{p.get('display_id')}: unknown/duplicate reason types")
    return errors


def reason_controls(prefix: str) -> str:
    return ('<fieldset><legend>你主要根据哪些内容作出判断？（可多选，见下方例外）</legend>'
            '<p class="note">通常至少选一类。若查询有歧义／无法判断、本段无法裁定，且已在本段补充说明中写明疑点，类别可以留空；不要强行选。类别不表示条件已满足。</p>'
            + "".join(f'<label><input type="checkbox" id="{prefix}-basis-{key}" value="{key}"> '
                      f'{html.escape(label)}</label>' for key, label in REASON_TYPES.items()) + '</fieldset>')


def pair_reason_control(prefix: str = "") -> str:
    options = '<option value="">请选择</option>' + ''.join(
        f'<option value="{key}">{html.escape(label)}</option>' for key, label in PAIR_REASON_CODES.items())
    return (f'<label>比较依据（必填，不自动决定哪段更好）<select id="{prefix}pair-reason-code">{options}</select></label>'
            f'<p id="{prefix}pair-requirements" class="note"></p>')


REASON_LOGIC_JS = r"""
function structuredMissing(a){
 const missing=[];
 for(const p of a.paragraphs){
  const s=p.display_id,kinds=p.reason_types||[],note=(p.reason||'').trim();
  const ambiguityAbstention=reasonContract.reason_types_optional_query_ambiguity.includes(a.query_ambiguity)
   &&p.applicability===reasonContract.reason_types_optional_applicability&&!!note;
  if(!kinds.length&&!ambiguityAbstention)missing.push(s+'.reason_types');
  if(reasonContract.evidence_required_for.includes(p.applicability)&&!p.evidence_spans.length)missing.push(s+'.evidence');
  if((reasonContract.paragraph_note_required_for.includes(p.applicability)||kinds.some(k=>reasonContract.paragraph_note_required_types.includes(k)))&&!note)missing.push(s+'.specific_uncertainty');
  if(p.applicability===reasonContract.insufficient_applicability&&!kinds.some(k=>reasonContract.content_types.includes(k))&&!note)missing.push(s+'.missing_information_type_or_note');
 }
 const code=a.pair_reason_code,note=(a.pair_reason||'').trim();
 if(!code)missing.push('pair_reason_code');
 const needs=reasonContract.pair_note_required_codes.includes(code)||['yes','uncertain'].includes(a.query_ambiguity)
  ||a.pair_preference==='undetermined'||(reasonContract.same_level_pair_codes.includes(code)&&['X','Y'].includes(a.pair_preference))
  ||(reasonContract.asymmetric_pair_codes.includes(code)&&a.pair_preference==='tie');
 if(needs&&!note)missing.push('pair_specific_note');
 return missing;
}
function structuredShape(a){
 if(a.answer_schema_version!==2)throw Error('单题格式版本不正确');
 if(a.pair_reason_code!==null&&a.pair_reason_code!==''&&(typeof a.pair_reason_code!=='string'||!Object.hasOwn(reasonContract.pair_reason_codes,a.pair_reason_code)))throw Error('比较依据选项不正确');
 for(const p of a.paragraphs){
  if(!Array.isArray(p.reason_types)||p.reason_types.some(k=>typeof k!=='string'||!Object.hasOwn(reasonContract.reason_types,k))||new Set(p.reason_types).size!==p.reason_types.length)throw Error('依据类型含未知或重复选项');
 }
}
const missingLabels={reason_types:'请选择至少一种判断依据',evidence:'支持／明确不满足时必须摘录原文',
 specific_uncertainty:'请简短说明具体疑点',missing_information_type_or_note:'请指出缺少的人物、行为、肯否、时间数量等信息类型，或补充说明',
 pair_reason_code:'请选择比较依据',pair_specific_note:'请简短解释歧义、特殊比较或其他原因'};
function missingText(k){const parts=k.split('.');return (parts.length===2?parts[0]+'：':'')+(missingLabels[parts.at(-1)]||k);}
"""
