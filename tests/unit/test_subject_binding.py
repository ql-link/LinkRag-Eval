from __future__ import annotations

import copy
from collections import Counter

import pytest

from linkrag_eval.retrieval.learning_to_rank.subject_binding import (
    SHUFFLE_SEEDS,
    atomic_match,
    cache_key,
    score_conditions,
    shuffled_subjects,
    text_hash,
)


def fact(subject, predicate, *, sentence=0, polarity="positive", modality=(), arguments=()):
    return {"subject_key": subject, "predicate": predicate, "arguments": list(arguments),
            "sentence_id": sentence, "polarity": polarity, "modality": list(modality),
            "evidence_offsets": [], "extraction_status": "usable"}


def query():
    return {"query_structure_supported": True, "conditions": [
        fact("variable:0", "sing"), fact("variable:0", "read", polarity="negative", modality=("can",))]}


def paragraph(facts):
    return {"text_sha256": text_hash("fixed test text"), "facts": facts, "extraction_incomplete": False}


def test_cross_sentence_same_subject_and_same_sentence_different_subject_are_separate():
    rows = [fact("name:mira", "sing", sentence=0),
            fact("name:mira", "read", sentence=1, polarity="negative", modality=("can",))]
    a = score_conditions(query(), paragraph(rows))
    assert (a["loose"], a["sentence"], a["entity"]) == (1, .5, 1)
    rows[1].update(subject_key="name:noah", sentence_id=0)
    b = score_conditions(query(), paragraph(rows))
    assert (b["loose"], b["sentence"], b["entity"]) == (1, 1, .5)


@pytest.mark.parametrize("change", [{"predicate": "dance"}, {"polarity": "positive"}, {"modality": []}])
def test_atomic_match_keeps_predicate_polarity_and_modality(change):
    condition = query()["conditions"][1]
    record = {**condition, "subject_key": "name:mira", **change}
    assert not atomic_match(condition, record)


def test_required_object_and_role_are_not_ignored():
    obj = {"role": "object", "lemmas": ["poem"]}
    c = fact("variable:0", "recite", arguments=[obj])
    assert atomic_match(c, fact("name:mira", "recite", arguments=[obj]))
    assert not atomic_match(c, fact("name:mira", "recite"))
    assert not atomic_match(c, fact("name:mira", "recite", arguments=[{**obj, "role": "complement"}]))


def test_explicit_subject_is_atomic_constraint():
    assert not atomic_match(fact("name:mira", "sing"), fact("name:noah", "sing"))


def test_unsupported_query_and_empty_facts_are_missing_not_negative_labels():
    q = query()
    q["query_structure_supported"] = False
    a = score_conditions(q, paragraph([fact("name:mira", "sing")]))
    assert a["entity"] is None and a["availability"] == "query_unsupported"
    b = score_conditions(query(), paragraph([]))
    assert b["entity"] is None and b["extraction_incomplete"] == 1
    c = score_conditions(query(), paragraph([fact("name:mira", "dance")]))
    assert c["entity"] == 0 and c["availability"] == "available"
    assert "label" not in c


def test_partial_extraction_retains_candidate_and_available_evidence():
    p = paragraph([fact("name:mira", "sing")])
    p["extraction_incomplete"] = True
    r = score_conditions(query(), p)
    assert r["entity"] == .5 and r["extraction_incomplete"] == 1


@pytest.mark.parametrize("seed", SHUFFLE_SEEDS)
def test_shuffle_preserves_every_non_subject_field_and_subject_multiset(seed):
    p = paragraph([fact(f"name:{i % 3}", "read", sentence=i) for i in range(9)])
    old = copy.deepcopy(p)
    a, report = shuffled_subjects(p, seed)
    assert p == old
    assert Counter(f["subject_key"] for f in a["facts"]) == Counter(f["subject_key"] for f in p["facts"])
    assert [{k: v for k, v in f.items() if k != "subject_key"} for f in a["facts"]] == [
        {k: v for k, v in f.items() if k != "subject_key"} for f in p["facts"]]
    assert shuffled_subjects(p, seed) == (a, report)
    assert report["changed_records"] > 0


def test_single_subject_cannot_claim_effective_shuffle():
    p = paragraph([fact("name:mira", "sing"), fact("name:mira", "read")])
    shuffled, report = shuffled_subjects(p, SHUFFLE_SEEDS[0])
    assert shuffled == p and report["effective"] is False


def test_text_cache_does_not_normalize_unicode_or_whitespace():
    assert len({cache_key(t) for t in ("Cannot read.", "cannot read.", "cannot read. ", "can’t read.")}) == 4


def parsed_sentence(words):
    """Grammar fixtures specify parser tokens, never retrieval scores or human labels."""
    from linkrag_eval.retrieval.learning_to_rank.subject_binding import parser_contract
    text = " ".join(row[0] for row in words)
    tokens, offset = [], 0
    for i, (surface, lemma, pos, tag, dep, head) in enumerate(words):
        tokens.append({"i": i, "text": surface, "lemma": lemma, "pos": pos, "tag": tag, "dep": dep,
                           "head": head, "start": offset, "end": offset + len(surface), "sentence_id": 0})
        offset += len(surface) + 1
    return text, {"text_sha256": text_hash(text), "contract": parser_contract(), "tokens": tokens}


@pytest.mark.parametrize("surface,tag,expected", [("write", "VB", ["can"]), ("writes", "VBZ", [])])
def test_shared_modal_requires_bare_infinitive_and_retains_evidence(surface, tag, expected):
    from linkrag_eval.retrieval.learning_to_rank.subject_binding import extract
    text, parsed = parsed_sentence([
        ("Mira", "mira", "PROPN", "NNP", "nsubj", 2),
        ("can", "can", "AUX", "MD", "aux", 2),
        ("read", "read", "VERB", "VB", "ROOT", 2),
        ("and", "and", "CCONJ", "CC", "cc", 2),
        (surface, "write", "VERB", tag, "conj", 2),
    ])
    result = extract(text, parsed)
    second = result["facts"][1]
    assert second["modality"] == expected
    assert second["subject_key"] == result["facts"][0]["subject_key"]
    assert ("can" in [span["quote"] for span in second["evidence_offsets"]]) == bool(expected)
    for f in result["facts"]:
        for span in f["evidence_offsets"]:
            assert text[span["start"]:span["end"]] == span["quote"]


def test_unresolved_pronouns_are_not_attached_to_nearest_name():
    from linkrag_eval.retrieval.learning_to_rank.subject_binding import extract
    text, parsed = parsed_sentence([
        ("She", "she", "PRON", "PRP", "nsubj", 1),
        ("reads", "read", "VERB", "VBZ", "ROOT", 1),
    ])
    result = extract(text, parsed)
    assert result["facts"] == [] and result["extraction_incomplete"]
    assert result["issues"][0]["reason"] == "unresolved_pronoun_subject"
    assert extract(text, parsed, query=True)["query_structure_supported"] is False


def test_parser_cache_refuses_wrong_contract_or_unicode_offset():
    from linkrag_eval.retrieval.learning_to_rank.subject_binding import extract
    text, parsed = parsed_sentence([
        ("Míra", "míra", "PROPN", "NNP", "nsubj", 1),
        ("reads", "read", "VERB", "VBZ", "ROOT", 1),
    ])
    bad = copy.deepcopy(parsed)
    bad["contract"]["extraction_rules"] = "other"
    with pytest.raises(ValueError, match="contract"):
        extract(text, bad)
    parsed["tokens"][1]["start"] += 1
    with pytest.raises(ValueError, match="offsets"):
        extract(text, parsed)
