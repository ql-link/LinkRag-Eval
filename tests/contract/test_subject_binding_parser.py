"""Raw English → actual local spaCy → evidence records → matching → aggregation.

Grammar expectations are engineering tests, not human NevIR judgments. The existing
isolated parser runtime is optional in CI, but required and exercised in local delivery.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from linkrag_eval.retrieval.learning_to_rank.subject_binding import (
    RECORD_RULE_VERSION,
    REPAIRED_RULE_VERSION,
    extract,
    score_conditions,
    shuffled_subjects,
)
from linkrag_eval.retrieval.learning_to_rank.subject_binding_matching import StrictEvidenceMatcher

TEXTS = {
    "q": "Which film received favorable reviews?",
    "direct": "The film received favorable reviews.",
    "bad": "The film received unfavorable reviews.",
    "paraphrase": "The film received rave reviews.",
    "actor": "The actor received favorable reviews.",
    "possessive": "Her next film received unfavorable reviews.",
    "appositive": "Orion, a film, received favorable reviews.",
    "pronoun": "It received favorable reviews.",
    "antecedent": "The film premiered. It received favorable reviews.",
    "pronouns": "It taught physics. It studied chemistry.",
    "negative": "The film did not receive favorable reviews.",
    "qualified": "The film received extremely favorable reviews.",
    "q_parser_failure": "Which scientist taught physics and studied chemistry?",
    "q_multi": "Which scientist taught physics and did study chemistry?",
    "same": "Alice is a scientist. Alice taught physics. Alice studied chemistry.",
    "different": "Alice is a scientist. Alice taught physics. Bob is a scientist. Bob studied chemistry.",
    "same_sentence": "Alice is a scientist and taught physics, and Bob is a scientist and studied chemistry.",
    "coordinated": "Alice and Bob received favorable reviews.",
    "reported": 'Alice said, "The film received favorable reviews."',
    "complement": "Alice said that the film received favorable reviews.",
    "conditional": "If the film premieres, Alice will receive favorable reviews.",
    "conditional_conjunct": "If the film premieres, Alice will teach physics and Bob will study chemistry.",
    "partial_query": "Which film received favorable reviews and was released in June?",
    "q_young": "Which young actor received favorable reviews?",
    "shared_modal": "Alice can read and write.",
    "parser_modal_failure": "Alice can teach physics and study chemistry.",
}


@pytest.fixture(scope="session")
def actual_binding_tokens():
    root = Path(__file__).resolve().parents[2]
    executable = Path(os.environ.get("EVAL_BINDING_PARSER_PYTHON", str(
        root / "runs/post_recall/subject-binding-pilot-20260908/environment/parser/bin/python")))
    if not executable.exists():
        pytest.skip("real parser runtime unavailable; this is not a parser integration pass")
    code = """
import importlib.metadata, json, sys
import spacy
from linkrag_eval.retrieval.learning_to_rank.subject_binding import (
    PARSER_MODEL, PARSER_VERSION, SPACY_VERSION, serialize_doc,
)
assert spacy.__version__ == SPACY_VERSION
assert importlib.metadata.version(PARSER_MODEL) == PARSER_VERSION
texts = json.load(sys.stdin)
nlp = spacy.load(PARSER_MODEL, exclude=['ner'])
print(json.dumps({name: serialize_doc(nlp(text)) for name, text in texts.items()}))
"""
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    result = subprocess.run([str(executable), "-c", code], input=json.dumps(TEXTS),
                            capture_output=True, text=True, cwd=root, env=env, timeout=60, check=True)
    return json.loads(result.stdout)


def parsed(actual, name, *, query=False, version=RECORD_RULE_VERSION):
    return extract(TEXTS[name], actual[name], query=query, rules_version=version)


def scores(actual, name, q="q"):
    return score_conditions(parsed(actual, q, query=True), parsed(actual, name))


def event(records, predicate):
    return next(r for r in records["facts"] if r["kind"] == "event" and r["predicate"] == predicate)


def test_direct_type_and_event_match_from_actual_raw_text(actual_binding_tokens):
    actual = actual_binding_tokens
    q = parsed(actual, "q", query=True)
    assert q["query_structure_supported"] and q["condition_count"] == 2
    assert {c["kind"] for c in q["conditions"]} == {"type", "event"}
    assert all(scores(actual, "direct")[k] == 1 for k in ("loose", "sentence", "entity"))
    # Show the actual asymmetry this repairs, without changing the historical version.
    old = score_conditions(parsed(actual, "q", query=True, version=REPAIRED_RULE_VERSION),
                           parsed(actual, "direct", version=REPAIRED_RULE_VERSION))
    assert old["entity"] == .5


def test_possessive_appositive_and_type_modifiers_are_not_deleted(actual_binding_tokens):
    actual = actual_binding_tokens
    r = event(parsed(actual, "possessive"), "receive")
    assert r["subject"]["head"] == "film" and r["subject"]["identity_status"] == "explicit"
    assert r["subject_key"].startswith("mention:")
    assert {m["dependency"] for m in r["subject"]["modifiers"]} >= {"poss", "amod"}
    assert r["arguments"][0]["head"] == "review"
    assert any(m["lemma"] == "unfavorable" for m in r["arguments"][0]["modifiers"])
    assert scores(actual, "appositive")["entity"] == 1
    q = parsed(actual, "q_young", query=True)
    type_condition = next(c for c in q["conditions"] if c["kind"] == "type")
    assert any(m["lemma"] == "young" for m in type_condition["arguments"][0]["modifiers"])
    assert scores(actual, "actor", q="q_young")["entity"] < 1


@pytest.mark.parametrize("name", ["pronoun", "antecedent"])
def test_pronoun_events_retained_but_no_antecedent_is_guessed(actual_binding_tokens, name):
    r = event(parsed(actual_binding_tokens, name), "receive")
    assert r["subject"]["identity_status"] == "unresolved"
    assert r["subject"]["binding_key"] is None
    assert r["assertion_status"] == "asserted"
    assert scores(actual_binding_tokens, name)["entity"] < 1
    assert r["evidence_offsets"] and r["subject"]["span"]["quote"] == "It"


def test_unknown_subjects_never_merge_even_after_shuffle(actual_binding_tokens):
    p = parsed(actual_binding_tokens, "pronouns")
    assert len(p["facts"]) == 2
    assert len({f["subject_key"] for f in p["facts"]}) == 2
    shuffled, report = shuffled_subjects(p, 42)
    assert shuffled == p and report["unresolved_records_unchanged"] == 2
    result = scores(actual_binding_tokens, "pronouns", q="q_multi")
    assert result["loose"] == pytest.approx(2 / 3)
    assert result["entity"] == pytest.approx(1 / 3)


@pytest.mark.parametrize("name", ["bad", "paraphrase", "qualified", "actor", "negative"])
def test_no_false_full_support_for_changed_review_or_object(actual_binding_tokens, name):
    assert scores(actual_binding_tokens, name)["entity"] < 1


def test_matcher_returns_evidence_and_distinguishes_conflict_from_unknown(actual_binding_tokens):
    q = parsed(actual_binding_tokens, "q", query=True)
    c = next(c for c in q["conditions"] if c["kind"] == "event")
    matcher = StrictEvidenceMatcher()
    for name, expected in (("direct", "support"), ("negative", "conflict"), ("paraphrase", "unknown")):
        fact = event(parsed(actual_binding_tokens, name), "receive")
        decision = matcher.match(c, fact)
        assert decision.status == expected and decision.evidence
        assert all(e in fact["evidence_offsets"] for e in decision.evidence)


def test_matcher_interface_is_replaceable_and_evidence_is_checked(actual_binding_tokens):
    from linkrag_eval.retrieval.learning_to_rank.subject_binding_matching import MatchDecision
    q, p = parsed(actual_binding_tokens, "q", query=True), parsed(actual_binding_tokens, "direct")

    class RecordingMatcher:
        version = "test_delegate_to_strict"

        def __init__(self):
            self.calls = []

        def match(self, condition, fact):
            self.calls.append((condition["fact_id"], fact["fact_id"]))
            return StrictEvidenceMatcher().match(condition, fact)

    matcher = RecordingMatcher()
    result = score_conditions(q, p, matcher=matcher)
    assert result["matcher_version"] == matcher.version and result["entity"] == 1
    assert len(matcher.calls) == len(q["conditions"]) * len(p["facts"])

    class InvalidEvidenceMatcher:
        version = "invalid_test_evidence"

        def match(self, condition, fact):
            return MatchDecision("support", "test", ({"start": 0, "end": 5, "quote": "fake!"},))

    with pytest.raises(ValueError, match="outside"):
        score_conditions(q, p, matcher=InvalidEvidenceMatcher())


def test_binding_and_sentence_aggregation_differ_after_real_parser(actual_binding_tokens):
    same = scores(actual_binding_tokens, "same", q="q_multi")
    different = scores(actual_binding_tokens, "different", q="q_multi")
    sentence = scores(actual_binding_tokens, "same_sentence", q="q_multi")
    assert same["loose"] == same["entity"] == 1 and same["sentence"] < 1
    assert different["loose"] == 1 and different["entity"] == pytest.approx(2 / 3)
    assert sentence["loose"] == sentence["sentence"] == 1
    assert sentence["entity"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("name", ["reported", "complement", "conditional", "coordinated"])
def test_uncertain_scope_is_preserved_without_promoting_assertions(actual_binding_tokens, name):
    p = parsed(actual_binding_tokens, name)
    assert p["facts"] and p["unresolved_restrictions"]
    assert any(f["assertion_status"] == "uncertain" and f["evidence_span"] for f in p["facts"])
    assert scores(actual_binding_tokens, name)["entity"] is None


def test_partial_query_keeps_unresolved_condition_and_never_shrinks_denominator(actual_binding_tokens):
    q = parsed(actual_binding_tokens, "partial_query", query=True)
    assert {c["predicate"] for c in q["conditions"]} >= {"receive", "release"}
    assert q["unresolved_restrictions"] and not q["query_structure_supported"]
    assert scores(actual_binding_tokens, "direct", q="partial_query")["loose"] is None


def test_conjunct_cannot_escape_a_governing_conditional(actual_binding_tokens):
    p = parsed(actual_binding_tokens, "conditional_conjunct")
    assert event(p, "study")["assertion_status"] == "uncertain"
    assert event(p, "study")["scope_issues"]


def test_inherited_subject_and_modal_keep_their_own_source_evidence(actual_binding_tokens):
    r = event(parsed(actual_binding_tokens, "shared_modal"), "write")
    assert r["modality"] == ["can"] and r["subject_key"] == "name:alice"
    assert {e["quote"] for e in r["evidence_offsets"]} >= {"Alice", "can", "write"}


def test_unrecognized_verbal_reading_remains_a_documented_parser_limit(actual_binding_tokens):
    p = parsed(actual_binding_tokens, "parser_modal_failure")
    assert not any(f["predicate"] == "study" for f in p["facts"])
    assert any(e["quote"] == "study" for f in p["facts"] for e in f["evidence_offsets"])


def test_observed_parser_failure_is_preserved_instead_of_repairing_tokens(actual_binding_tokens):
    q = parsed(actual_binding_tokens, "q_parser_failure", query=True)
    assert not q["query_structure_supported"]
    assert any(c["predicate"] == "study" for c in q["conditions"])
    assert scores(actual_binding_tokens, "same", q="q_parser_failure")["entity"] is None


def test_all_record_evidence_uses_original_unicode_offsets(actual_binding_tokens):
    for name, text in TEXTS.items():
        record = parsed(actual_binding_tokens, name, query=name.startswith("q") or name == "partial_query")

        def check(value, original=text):
            if isinstance(value, dict):
                if {"start", "end", "quote"} <= value.keys():
                    assert original[value["start"]:value["end"]] == value["quote"]
                for child in value.values():
                    check(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    check(child)
        check(record)
