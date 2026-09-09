"""Evidence-bearing support/conflict/unknown interface, with a strict local baseline.

No paraphrase or coreference model is installed or called here. A replacement must
identify its version; exported model contracts continue to require the chosen matcher.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .subject_binding import RECORD_RULE_VERSION
from .subject_binding_records import RECORD_SCHEMA

STRICT_MATCHER_VERSION = "strict_structured_evidence_v1"


@dataclass(frozen=True)
class MatchDecision:
    status: Literal["support", "conflict", "unknown"]
    reason: str
    evidence: tuple[dict, ...]

    def __post_init__(self):
        if self.status not in {"support", "conflict", "unknown"}:
            raise ValueError("invalid matching decision")


class EvidenceMatcher(Protocol):
    version: str

    def match(self, condition: dict, fact: dict) -> MatchDecision: ...


def argument_signature(argument):
    return (argument["role"], argument["head"], tuple(sorted(
        (m["dependency"], m["head_lemma"], m["lemma"]) for m in argument["modifiers"])))


def _same_word(a, a_surface, b, b_surface):
    # An identical original word must not fail only because the parser supplied
    # inconsistent lemmas (e.g. physics/physic). This is lexical, not paraphrase matching.
    return a == b or bool(a_surface and b_surface and a_surface.casefold() == b_surface.casefold())


def _same_argument(a, b):
    if argument_signature(a) == argument_signature(b):
        return True
    if a["role"] != b["role"] or not _same_word(a["head"], a.get("head_surface"), b["head"], b.get("head_surface")):
        return False
    remaining = list(b["modifiers"])
    for left in a["modifiers"]:
        match = next((right for right in remaining if left["dependency"] == right["dependency"]
                      and _same_word(left["lemma"], left.get("surface"), right["lemma"], right.get("surface"))
                      and _same_word(left["head_lemma"], left.get("head_surface"), right["head_lemma"], right.get("head_surface"))), None)
        if match is None:
            return False
        remaining.remove(match)
    return not remaining


class StrictEvidenceMatcher:
    version = STRICT_MATCHER_VERSION

    def match(self, condition, fact):
        def decision(status, reason):
            return MatchDecision(status, reason, tuple(fact["evidence_offsets"]))

        if condition["assertion_status"] != "asserted" or fact["assertion_status"] != "asserted":
            return decision("unknown", "unresolved_assertion_scope")
        if condition["subject_key"].startswith("name:") and condition["subject_key"] != fact["subject_key"]:
            return decision("unknown", "explicit_subject_not_matched")
        if any(condition[k] != fact[k] for k in ("kind", "predicate", "voice", "modality")):
            return decision("unknown", "predicate_type_voice_or_modality_mismatch")
        # Compare head/role/modifiers independently of raw span text. All modifiers are
        # retained: paraphrases and extra qualifiers stay unknown in this strict arm.
        remaining = list(fact["arguments"])
        for required in condition["arguments"]:
            matched = next((a for a in remaining if _same_argument(required, a)), None)
            if matched is None:
                return decision("unknown", "argument_head_role_or_modifier_mismatch")
            remaining.remove(matched)
        if remaining:
            return decision("unknown", "additional_argument_or_qualifier")
        if condition["polarity"] != fact["polarity"]:
            return decision("conflict", "explicit_opposite_polarity")
        return decision("support", "strict_structured_match")


def score_records(query, paragraph, *, matcher: EvidenceMatcher | None = None):
    if (query.get("rules_version") != RECORD_RULE_VERSION or paragraph.get("rules_version") != RECORD_RULE_VERSION
            or query.get("record_schema") != RECORD_SCHEMA or paragraph.get("record_schema") != RECORD_SCHEMA):
        raise ValueError("evidence record schema/version mismatch")
    matcher = matcher or StrictEvidenceMatcher()
    if not isinstance(matcher.version, str) or not matcher.version:
        raise ValueError("matcher must declare an explicit version")
    supported = query["query_structure_supported"]
    facts = [f for f in paragraph["facts"] if f["assertion_status"] == "asserted"]
    result = {"rules_version": RECORD_RULE_VERSION, "matcher_version": matcher.version,
              "query_structure_supported": int(supported),
              "extraction_incomplete": int(paragraph["extraction_incomplete"] or not facts),
              "loose": None, "sentence": None, "entity": None,
              "availability": "query_unsupported" if not supported else "no_usable_facts"}
    if not supported or not query["conditions"] or not facts:
        return result
    evidence_keys = [{(e["start"], e["end"], e["quote"]) for e in f["evidence_offsets"]} for f in facts]
    matrix = []
    for condition in query["conditions"]:
        row = []
        for fact, allowed in zip(facts, evidence_keys, strict=True):
            decision = matcher.match(condition, fact)
            if not isinstance(decision, MatchDecision):
                raise TypeError("matcher must return an evidence-bearing MatchDecision")
            if any((e["start"], e["end"], e["quote"]) not in allowed for e in decision.evidence):
                raise ValueError("matcher evidence is outside the supplied fact")
            if decision.status != "unknown" and not decision.evidence:
                raise ValueError("support/conflict requires evidence")
            row.append(decision.status == "support")
        matrix.append(row)

    def coverage(indices):
        return sum(any(row[i] for i in indices) for row in matrix) / len(matrix)

    loose = coverage(range(len(facts)))
    sentence = max(coverage([i for i, f in enumerate(facts) if f["sentence_id"] == sid])
                   for sid in {f["sentence_id"] for f in facts})
    groups = {}
    for i, fact in enumerate(facts):
        # Unknown identities are isolated per event/type record. Repeating "it" does
        # not permit cross-fact binding, even when the mention strings are identical.
        key = fact["subject"]["binding_key"] or f"unbound:{fact['fact_id']}"
        groups.setdefault(key, []).append(i)
    entity = max(coverage(indices) for indices in groups.values())
    if sentence > loose or entity > loose:
        raise ValueError("aggregation invariant violated")
    return {**result, "loose": loose, "sentence": sentence, "entity": entity,
            "availability": "available"}
