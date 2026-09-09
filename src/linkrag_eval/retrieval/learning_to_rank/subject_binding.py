"""Frozen lexical subject-binding pilot; no IDs, labels, retrieval or learned matcher.

The parser adapter supplies tokens and sentence boundaries for one unmodified text.
Unsupported syntax remains visible; absence of lexical support is never a negative label.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter

RULE_VERSION = "subject_binding_basic_v1"
REPAIRED_RULE_VERSION = "subject_binding_nominal_quotes_v2"
RECORD_RULE_VERSION = "subject_binding_evidence_records_v3"
RULE_VERSIONS = (RULE_VERSION, REPAIRED_RULE_VERSION, RECORD_RULE_VERSION)
GATE_VERSION = "within_query_aggregation_contrast_v2"
PARSER_MODEL = "en_core_web_sm"
PARSER_VERSION = "3.8.0"
SPACY_VERSION = "3.8.16"
SHUFFLE_SEEDS = (202609081, 202609082, 202609083)
MODALS = frozenset({"can", "could", "may", "might", "must", "shall", "should", "will", "would"})
SUBJECT_DEPS = frozenset({"nsubj", "nsubjpass", "csubj", "csubjpass"})
ARG_DEPS = frozenset({"dobj", "obj", "iobj", "dative", "attr", "acomp", "oprd", "prep", "prt"})
NESTED_CLAUSES = frozenset({"ccomp", "xcomp", "advcl", "acl", "relcl"})


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parser_contract() -> dict:
    # Frozen token-producer contract. Its historical extraction_rules field is retained
    # to verify existing token caches; the selected extractor is versioned separately.
    return {"model": PARSER_MODEL, "model_version": PARSER_VERSION,
            "spacy_version": SPACY_VERSION, "extraction_rules": RULE_VERSION,
            "components_used": ["lemma", "dependency", "sentence"],
            "text_policy": "full original Unicode text; no normalization or truncation"}


def cache_key(text: str) -> str:
    return text_hash(json.dumps([parser_contract(), text_hash(text)], sort_keys=True))


def serialize_doc(doc) -> dict:
    sentence_for = {token.i: index for index, sentence in enumerate(doc.sents) for token in sentence}
    return {"text_sha256": text_hash(doc.text), "contract": parser_contract(),
            "tokens": [{"i": t.i, "text": t.text, "lemma": t.lemma_.lower(), "pos": t.pos_,
                        "tag": t.tag_, "dep": t.dep_, "head": t.head.i,
                        "start": t.idx, "end": t.idx + len(t.text), "sentence_id": sentence_for[t.i]}
                       for t in doc]}


def validate_rules_version(rules_version: str) -> str:
    if rules_version not in RULE_VERSIONS:
        raise ValueError("unknown subject-binding extraction rules version")
    return rules_version


def _unsafe_quote_sentences(tokens):
    """Only matched, non-clausal nominal double quotes may bypass the old guard.

    This preserves title arguments without asserting the contents of reported speech.
    Unbalanced, nested, cross-sentence and verbal quotes remain unsupported.
    """
    quoted, unsafe, opening, content = set(), set(), None, []
    for token in tokens:
        mark, sid = token["text"], token["sentence_id"]
        if mark in {'"', '“', '”'}:
            quoted.add(sid)
            if opening is None:
                if mark == '”':
                    unsafe.add(sid)
                else:
                    opening, content = token, []
            elif (opening["text"], mark) in {('"', '"'), ('“', '”')}:
                nominal = (opening["sentence_id"] == sid
                           and any(t["pos"] in {"NOUN", "PROPN"} for t in content)
                           and all(t["pos"] in {"NOUN", "PROPN", "ADJ", "ADP", "DET",
                                                "NUM", "CCONJ", "PART", "PUNCT", "SPACE"}
                                   and t["dep"] not in NESTED_CLAUSES for t in content))
                if not nominal:
                    unsafe.update(t["sentence_id"] for t in [opening, *content, token])
                opening, content = None, []
            else:
                unsafe.update({sid, opening["sentence_id"]})
        elif opening is not None:
            content.append(token)
    if opening is not None:
        unsafe.update(t["sentence_id"] for t in [opening, *content])
    return quoted, unsafe


def extract(text: str, parsed: dict, *, query: bool = False, rules_version=RULE_VERSION) -> dict:
    validate_rules_version(rules_version)
    if parsed["text_sha256"] != text_hash(text) or parsed["contract"] != parser_contract():
        raise ValueError("parser text/version contract mismatch")
    tokens = parsed["tokens"]
    quoted, unsafe_quotes = _unsafe_quote_sentences(tokens)
    children = {t["i"]: [] for t in tokens}
    for i, t in enumerate(tokens):
        if t["i"] != i or text[t["start"]:t["end"]] != t["text"]:
            raise ValueError("token identity/Unicode offsets mismatch")
        if t["head"] != i:
            children[t["head"]].append(i)
    if rules_version == RECORD_RULE_VERSION:
        from .subject_binding_records import extract_records
        return extract_records(text, tokens, children, query=query)
    issues: list[dict] = []

    def issue(reason, index):
        issues.append({"reason": reason, "token_index": index,
                       "offset": tokens[index]["start"] if index is not None else None})

    def descendants(index):
        result = [index]
        for child in children[index]:
            result.extend(descendants(child))
        return sorted(result)

    def phrase(index):
        ids = descendants(index)
        if any(tokens[i]["pos"] in {"VERB", "AUX", "PRON"}
               or tokens[i]["dep"] in NESTED_CLAUSES | {"conj"} for i in ids):
            raise ValueError("complex_or_pronominal_argument")
        words = tuple(tokens[i]["lemma"] for i in ids
                      if tokens[i]["dep"] not in {"det", "punct"} and tokens[i]["pos"] != "SPACE")
        return words, ids

    def subject(predicate, trail=()):
        if predicate in trail:
            raise ValueError("subject_cycle")
        t = tokens[predicate]
        subs = [i for i in children[predicate] if tokens[i]["dep"] in SUBJECT_DEPS]
        if len(subs) == 1:
            s = subs[0]
            if tokens[s]["dep"] != "nsubj":
                raise ValueError("passive_or_clausal_subject")
            if any(tokens[i]["dep"] in {"conj", "poss", "appos"} for i in children[s]):
                raise ValueError("compound_or_qualified_subject")
            # Relative pronouns can point to their explicit grammatical antecedent.
            if (tokens[s]["lemma"] in {"who", "which", "that"}
                    and t["dep"] == "relcl"):
                s = t["head"]
            st = tokens[s]
            modifiers = [i for i in children[s] if tokens[i]["dep"] in {"compound", "amod", "flat"}]
            name_ids = sorted([s, *modifiers])
            wh = st["lemma"] in {"who", "what"} or any(
                tokens[i]["lemma"] in {"which", "what"} and tokens[i]["dep"] == "det"
                for i in children[s])
            if query and wh:
                # A noun in "which composer" is a required type condition, not discarded.
                kind = tuple(tokens[i]["lemma"] for i in name_ids) if st["pos"] == "NOUN" else ()
                return f"variable:{s}", name_ids, kind
            if st["pos"] == "PRON" or st["lemma"] in {"who", "what", "which", "that"}:
                raise ValueError("unresolved_pronoun_subject")
            if st["pos"] == "PROPN" and all(tokens[i]["pos"] == "PROPN" for i in name_ids):
                return "name:" + " ".join(tokens[i]["lemma"] for i in name_ids), name_ids, ()
            if query:
                raise ValueError("query_subject_not_identified")
            if st["pos"] == "NOUN":
                return f"mention:{st['start']}", name_ids, ()
            raise ValueError("subject_not_identified")
        if not subs and t["dep"] == "conj" and tokens[t["head"]]["pos"] in {"VERB", "AUX"}:
            inherited = subject(t["head"], (*trail, predicate))
            if any(tokens[i]["dep"] == "neg" for i in children[t["head"]]):
                raise ValueError("ambiguous_inherited_negation_scope")
            return inherited
        raise ValueError("missing_or_multiple_subjects")

    facts, query_kinds = [], {}
    predicates = [t["i"] for t in tokens if t["pos"] in {"VERB", "AUX"}
                  and t["dep"] not in {"aux", "auxpass", "cop"}]
    for index in predicates:
        t = tokens[index]
        local = children[index]
        try:
            quote_guard = quoted if rules_version == RULE_VERSION else unsafe_quotes
            if t["sentence_id"] in quote_guard:
                raise ValueError("quoted_statement_scope")
            if t["dep"] not in {"ROOT", "conj", "relcl"}:
                raise ValueError("unsupported_embedded_clause")
            if any(tokens[i]["dep"] in NESTED_CLAUSES - {"relcl"} for i in local):
                raise ValueError("unsupported_clause_complement")
            if any(tokens[i]["dep"] == "auxpass" for i in local):
                raise ValueError("passive_voice")
            if any(tokens[i]["lemma"] in {"if", "unless", "whether", "or", "either", "neither"}
                   for i in descendants(index) if tokens[i]["dep"] in {"mark", "cc", "preconj"}):
                raise ValueError("unsupported_condition_or_disjunction")
            sid, subject_ids, kind = subject(index)
            query_kinds[sid] = kind
            negations = [i for i in local if tokens[i]["dep"] == "neg" or tokens[i]["lemma"] == "never"]
            if len(negations) > 1 or (negations and any(tokens[i]["lemma"] == "only" for i in local)):
                raise ValueError("complex_negation_scope")
            auxiliaries = [i for i in local if tokens[i]["dep"] == "aux"]
            modality = tuple(tokens[i]["lemma"] for i in auxiliaries if tokens[i]["lemma"] in MODALS)
            # A positive shared auxiliary is inherited only under explicit coordination.
            if t["dep"] == "conj" and t["tag"] == "VB" and not auxiliaries and not any(
                    tokens[i]["dep"] in SUBJECT_DEPS for i in local):
                head = t["head"]
                inherited_aux = [i for i in children[head]
                                 if tokens[i]["dep"] == "aux" and tokens[i]["lemma"] in MODALS]
                modality = tuple(tokens[i]["lemma"] for i in inherited_aux)
                auxiliaries.extend(inherited_aux)
            args, evidence_ids = [], {index, *subject_ids, *negations, *auxiliaries}
            for child in local:
                dep = tokens[child]["dep"]
                if dep in ARG_DEPS or (dep == "advmod" and child not in negations):
                    words, ids = phrase(child)
                    args.append({"role": "object" if dep in {"dobj", "obj"} else dep,
                                 "lemmas": list(words)})
                    evidence_ids.update(ids)
            # Nominal and adjectival copular complements share a lexical complement role.
            for arg in args:
                if t["lemma"] == "be" and arg["role"] in {"attr", "acomp", "oprd"}:
                    arg["role"] = "complement"
            if t["lemma"] == "be" and not args:
                raise ValueError("missing_copular_complement")
            facts.append({"subject_key": sid, "predicate": t["lemma"], "arguments": args,
                          "polarity": "negative" if negations else "positive",
                          "modality": list(modality), "sentence_id": t["sentence_id"],
                          "evidence_offsets": [{"start": tokens[i]["start"], "end": tokens[i]["end"],
                                                "quote": text[tokens[i]["start"]:tokens[i]["end"]]}
                                               for i in sorted(evidence_ids)],
                          "extraction_status": "usable"})
        except ValueError as error:
            issue(str(error), index)
    if not predicates:
        issue("no_predicate", None)
    if query:
        if len({t["sentence_id"] for t in tokens}) != 1:
            issue("multi_sentence_query", None)
        subjects = {f["subject_key"] for f in facts}
        if len(subjects) != 1:
            issue("no_single_shared_query_subject", None)
        for sid, kind in query_kinds.items():
            if kind:
                facts.append({"subject_key": sid, "predicate": "be",
                              "arguments": [{"role": "complement", "lemmas": list(kind)}],
                              "polarity": "positive", "modality": [], "sentence_id": 0,
                              "evidence_offsets": [], "extraction_status": "usable"})
        # Distinct conditions only; repetition must not create K>=2.
        seen, conditions = set(), []
        for f in facts:
            signature = json.dumps([f[k] for k in ("subject_key", "predicate", "arguments", "polarity", "modality")], sort_keys=True)
            if signature not in seen:
                seen.add(signature)
                conditions.append(f)
        if len(conditions) < 2:
            issue("fewer_than_two_conditions", None)
        return {"text_sha256": text_hash(text), "rules_version": rules_version,
                "conditions": conditions, "condition_count": len(conditions),
                "query_structure_supported": not issues,
                "explicit_subject_constraint": bool(subjects) and all(s.startswith("name:") for s in subjects),
                "issues": issues, "status": "supported" if not issues else "unsupported"}
    return {"text_sha256": text_hash(text), "rules_version": rules_version, "facts": facts,
            "extraction_incomplete": bool(issues) or not facts, "issues": issues,
            "status": "incomplete" if issues or not facts else "complete"}


def atomic_match(condition: dict, fact: dict) -> bool:
    if condition["subject_key"].startswith("name:") and condition["subject_key"] != fact["subject_key"]:
        return False
    if any(condition[k] != fact[k] for k in ("predicate", "polarity", "modality")):
        return False
    return all(arg in fact["arguments"] for arg in condition["arguments"])


def score_conditions(query: dict, paragraph: dict, *, matcher=None) -> dict:
    if query.get("rules_version") != paragraph.get("rules_version"):
        raise ValueError("query/paragraph extraction rules mismatch")
    if query.get("rules_version") == RECORD_RULE_VERSION:
        from .subject_binding_matching import score_records
        return score_records(query, paragraph, matcher=matcher)
    if matcher is not None:
        raise ValueError("legacy rules do not accept a replacement matcher")
    supported = query["query_structure_supported"]
    facts = [f for f in paragraph["facts"] if f["extraction_status"] == "usable"]
    result = {"query_structure_supported": int(supported),
              "extraction_incomplete": int(paragraph["extraction_incomplete"] or not facts),
              "loose": None, "sentence": None, "entity": None,
              "availability": "query_unsupported" if not supported else "no_usable_facts"}
    if query.get("rules_version") == REPAIRED_RULE_VERSION:
        result["rules_version"] = REPAIRED_RULE_VERSION
    if not supported or len(query["conditions"]) < 2 or not facts:
        return result
    def coverage(group):
        return sum(any(atomic_match(c, f) for f in group) for c in query["conditions"]) / len(query["conditions"])
    loose = coverage(facts)
    scores = {name: max(coverage([f for f in facts if f[key] == value])
                        for value in {f[key] for f in facts})
              for name, key in (("sentence", "sentence_id"), ("entity", "subject_key"))}
    if scores["sentence"] > loose or scores["entity"] > loose:
        raise ValueError("aggregation invariant violated")
    return {**result, **scores, "loose": loose, "availability": "available"}


def training_signal_gate(by_query: dict, *, purpose="binding") -> dict:
    """Check numeric candidate contrasts, never labels or cross-query status variation.

    Use complete pools for development and only legal supervised rows for training.
    Both stages must pass before fitting an aggregation comparison. Missingness alone
    and an arm-specific constant offset cannot establish an aggregation contrast.
    """
    if purpose not in {"basic_matching", "binding"}:
        raise ValueError("unknown training comparison purpose")
    numeric, aggregation = [], []
    for qid, rows in by_query.items():
        values = []
        for row in rows:
            scores = tuple(row[k] for k in ("loose", "sentence", "entity"))
            if all(v is None for v in scores):
                continue
            if (row["query_structure_supported"] != 1 or row["availability"] != "available"
                    or any(v is None or not math.isfinite(v) or not 0 <= v <= 1 for v in scores)):
                raise ValueError("invalid numeric aggregation signal")
            values.append(scores)
        if any(len({v[i] for v in values}) > 1 for i in range(3)):
            numeric.append(qid)
        if any(values and any(not math.isclose(v[i] - v[j], values[0][i] - values[0][j],
                                               rel_tol=0.0, abs_tol=1e-12) for v in values[1:])
               for i, j in ((0, 1), (0, 2), (1, 2))):
            aggregation.append(qid)
    allowed = bool(numeric and (purpose == "basic_matching" or aggregation))
    return {"version": GATE_VERSION, "queries": len(by_query),
            "purpose": purpose,
            "numeric_contrast_queries": numeric, "aggregation_contrast_queries": aggregation,
            "allowed": allowed,
            "stop_reason": None if allowed else "no_within_query_numeric_contrast" if not numeric
            else "no_within_query_aggregation_contrast"}


def shuffled_subjects(paragraph: dict, seed: int) -> tuple[dict, dict]:
    if paragraph.get("rules_version") == RECORD_RULE_VERSION:
        # Leave unresolved identities isolated. Only known binding assignments form
        # the perturbation population; raw mentions/evidence are never rewritten.
        indices = [i for i, f in enumerate(paragraph["facts"]) if f["subject"]["binding_key"] is not None]
        subset = {**paragraph, "rules_version": REPAIRED_RULE_VERSION,
                  "facts": [paragraph["facts"][i] for i in indices]}
        permuted, report = shuffled_subjects(subset, seed)
        facts = list(paragraph["facts"])
        for i, fact in zip(indices, permuted["facts"], strict=True):
            facts[i] = {**fact, "subject": {**fact["subject"], "binding_key": fact["subject_key"]}}
        return {**paragraph, "facts": facts}, {**report, "unresolved_records_unchanged": len(facts) - len(indices)}
    facts = paragraph["facts"]
    before = [f["subject_key"] for f in facts]
    after = list(before)
    rng = random.Random(int(text_hash(f"{paragraph['text_sha256']}:{seed}"), 16))
    rng.shuffle(after)
    changed = sum(a != b for a, b in zip(before, after, strict=True))
    if Counter(before) != Counter(after):
        raise ValueError("shuffle changed subject marginals")
    result = {**paragraph, "facts": [{**f, "subject_key": s}
                                    for f, s in zip(facts, after, strict=True)]}
    return result, {"changed_records": changed, "total_records": len(facts),
                    "effective": changed > 0, "distinct_subjects": len(set(before))}
