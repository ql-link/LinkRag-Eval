"""English lexical expectations are ordinary examples, independent of NevIR scores."""
from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank import english_rules as en
from linkrag_eval.retrieval.learning_to_rank.features import (
    _CLAUSE_SPLIT_RE,
    _IDENTIFIER_RE,
    ENGLISH_FEATURE_VERSION,
    FEATURE_NAMES,
    FEATURE_VERSION,
    FeatureContractError,
    _condition_coverage,
    _ngrams,
    build_online_features,
)


@pytest.mark.parametrize("text,expected", [
    ("NOT", {"not"}), ("cannot", {"not"}), ("CANNOT", {"not"}),
    ("Isn't", {"not"}), ("isn’t", {"not"}), ("isn‘t", {"not"}), ("ISNʼT", {"not"}),
    ("no NEVER neither NOR without", {"no", "never", "neither", "nor", "without"}),
    ("knot notable cannotation nothing northern", set()),
    ("not_a_token anot not2", set()), ("The item is approved.", set()),
    ("'not'; (cannot)!", {"not"}), ("hardly barely", set()),
])
def test_negation_tokens_and_boundaries(text, expected):
    assert en.negations(text) == expected


@pytest.mark.parametrize("text", en.NEGATIVE_CONTRACTIONS)
def test_declared_contractions_are_equivalent_to_not(text):
    for spelling in (text, text.upper(), text.replace("'", "’")):
        assert en.negations(spelling) == {"not"}
        assert en.negations("prefix" + spelling + "suffix") == set()


@pytest.mark.parametrize("text,expected", [
    ("Alpha is ready. Beta is ready.", ["Alpha is ready", "Beta is ready"]),
    ("Dr. Lee paid 3.14. Beta is ready.", ["Dr. Lee paid 3.14", "Beta is ready"]),
    ("A U.S. item costs 1,234.50.", ["A U.S. item costs 1,234.50"]),
    ("Use e.g. blue AND red, BUT IF ready; proceed!", ["Use e.g. blue", "red", "ready", "proceed"]),
    ("J. Smith uses v2.1. Go now.", ["J. Smith uses v2.1", "Go now"]),
    ("candy butter gift", ["candy butter gift"]),
    ("Alpha, Beta?", ["Alpha", "Beta"]),
])
def test_surface_clauses_protect_decimal_abbreviation_and_word_boundaries(text, expected):
    assert en.clauses(text, _CLAUSE_SPLIT_RE) == expected


@pytest.mark.parametrize("text,expected", [
    ("3.14 and 13.14", {"3.14", "13.14"}),
    ("1,234.50 1234.50", {"1234.50"}),
    ("12, 34", {"12", "34"}),
    ("2026-03-01", {"2026", "03", "01"}),
])
def test_numeric_tokens_preserve_values(text, expected):
    assert en.numbers(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("ABC-12.", {"abc-12"}), ("(abc-12),", {"abc-12"}),
    ("v2.1 and V2.10", {"v2.1", "v2.10"}),
    ("2026-03-01", {"2026-03-01"}), ("1,234.50", {"1234.50"}),
])
def test_identifiers_keep_internal_punctuation(text, expected):
    assert en.identifiers(text, _IDENTIFIER_RE) == expected


def _input(query, content):
    return {"query": query, "routes": {"dense": [{"chunk_id": "a", "doc_id": 1, "dataset_id": 1,
                                                "score": 0.8}], "sparse": [], "bm25": []},
            "candidate_contents": {"a": content}}


@pytest.mark.parametrize("query,content,feature,legacy,english", [
    ("not ready", "cannot be ready", "negation_overlap_coverage", 0, 1),
    ("not ready", "ready", "negation_mismatch", 0, 1),
    ("ready", "isn't ready", "negation_mismatch", 0, 1),
    ("not ready", "notable readiness", "negation_overlap_coverage", 0, 0),
    ("3.14", "13.14", "number_exact_coverage", 1, 0),
    ("12", "123", "number_exact_coverage", 1, 0),
    ("ABC-12", "ABC-123", "identifier_exact_coverage", 1, 0),
    ("ABC-12.", "ABC-12 is ready.", "identifier_exact_coverage", 0, 1),
    ("1,234.50", "1234.50", "number_exact_coverage", 1, 1),
    ("Alpha ready. Beta ready.", "Alpha ready. Beta ready.", "condition_coverage", 0, 1),
    ("Count 1,234.50.", "Count 1,234.50.", "condition_coverage", 1, 0),
])
def test_only_checked_feature_semantics_change(query, content, feature, legacy, english):
    kwargs = _input(query, content)
    original = deepcopy(kwargs)
    ids, old = build_online_features(**kwargs)
    explicit_ids, explicit = build_online_features(**kwargs, feature_version=FEATURE_VERSION)
    new_ids, new = build_online_features(**kwargs, feature_version=ENGLISH_FEATURE_VERSION)
    np.testing.assert_array_equal(old, explicit)
    assert ids == new_ids == explicit_ids and kwargs == original
    assert old.dtype == new.dtype == np.float32 and old.shape == new.shape == (1, 38)
    index = FEATURE_NAMES.index(feature)
    assert old[0, index] == legacy and new[0, index] == english
    allowed = {"identifier_exact_coverage", "number_exact_coverage", "negation_overlap_coverage",
               "negation_mismatch", "condition_coverage"}
    for i, name in enumerate(FEATURE_NAMES):
        if name not in allowed:
            assert old[0, i] == new[0, i], name
    np.testing.assert_array_equal(old, build_online_features(**kwargs)[1])


def test_ngram_case_apostrophe_equivalence_and_unknown_version():
    assert _ngrams("ISN'T", 2) == _ngrams("isn’t", 2)
    assert _ngrams("v2.1", 2) == _ngrams("V2.1", 2)
    with pytest.raises(FeatureContractError, match="unknown"):
        build_online_features(**_input("ready", "ready"), feature_version="auto")
    assert _condition_coverage("Dr. Lee paid 3.14.", "Dr. Lee paid 3.14.",
                               feature_version=ENGLISH_FEATURE_VERSION) == 0
