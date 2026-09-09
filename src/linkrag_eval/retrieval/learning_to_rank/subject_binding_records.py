"""V3 evidence records: retain uncertain events without granting them assertion or identity.

This consumes the same verified parser tokens as the historical extractors. No labels,
candidate IDs, external coreference model or synonym rules enter the representation.
"""
from __future__ import annotations

from .subject_binding import (
    ARG_DEPS,
    MODALS,
    NESTED_CLAUSES,
    RECORD_RULE_VERSION,
    SUBJECT_DEPS,
    _unsafe_quote_sentences,
    text_hash,
)

RECORD_SCHEMA = "subject_event_evidence_v1"
ARTICLES = frozenset({"a", "an", "the"})


def extract_records(text, tokens, children, *, query=False):
    def descendants(index, *, nominal=False):
        ids = [index]
        for child in children[index]:
            if not nominal or tokens[child]["dep"] not in NESTED_CLAUSES:
                ids.extend(descendants(child, nominal=nominal))
        return sorted(ids)

    def evidence(ids):
        return [{"start": tokens[i]["start"], "end": tokens[i]["end"], "quote": tokens[i]["text"]}
                for i in sorted(set(ids))]

    def span(ids):
        if not ids:
            return None
        start, end = min(tokens[i]["start"] for i in ids), max(tokens[i]["end"] for i in ids)
        return {"start": start, "end": end, "quote": text[start:end]}

    def phrase(index, role):
        ids = descendants(index)
        modifiers = []
        for i in ids:
            t = tokens[i]
            if i == index or t["dep"] == "punct" or t["pos"] == "SPACE":
                continue
            # Articles and the query operator are structural, not semantic modifiers.
            if t["dep"] == "det" and t["lemma"] in ARTICLES | {"which", "what"}:
                continue
            modifiers.append({"lemma": t["lemma"], "surface": t["text"], "dependency": t["dep"],
                              "head_lemma": tokens[t["head"]]["lemma"],
                              "head_surface": tokens[t["head"]]["text"], "evidence": evidence([i])})
        return {"role": role, "head": tokens[index]["lemma"], "head_surface": tokens[index]["text"], "modifiers": modifiers,
                "scope": [m for m in modifiers if m["dependency"] in {"neg", "mark", "preconj", "cc"}
                          or m["lemma"] in {"no", "only", "never"}],
                "lemmas": [tokens[i]["lemma"] for i in ids
                           if tokens[i]["dep"] != "punct" and tokens[i]["pos"] != "SPACE"],
                "span": span(ids), "evidence_offsets": evidence(ids)}

    def noun_type(index):
        # The explicit nominal head provides a lexical type; modifiers remain on the
        # mention and in type evidence, rather than changing the identity to its owner.
        modifier_ids = [j for i in children[index] if tokens[i]["dep"] in {"amod", "compound", "flat"}
                        for j in descendants(i)]
        ids = sorted([index, *modifier_ids])
        return {"role": "complement", "head": tokens[index]["lemma"], "head_surface": tokens[index]["text"],
                "modifiers": [{"lemma": tokens[i]["lemma"], "surface": tokens[i]["text"], "dependency": tokens[i]["dep"],
                               "head_lemma": tokens[tokens[i]["head"]]["lemma"],
                               "head_surface": tokens[tokens[i]["head"]]["text"], "evidence": evidence([i])}
                              for i in modifier_ids],
                "scope": [], "lemmas": [tokens[i]["lemma"] for i in ids],
                "span": span(ids), "evidence_offsets": evidence(ids)}

    def subject(predicate, trail=()):
        if predicate in trail:
            return None, ["subject_cycle"]
        local = children[predicate]
        subs = [i for i in local if tokens[i]["dep"] in SUBJECT_DEPS]
        if not subs and tokens[predicate]["dep"] == "conj":
            parent = tokens[predicate]["head"]
            inherited, reasons = subject(parent, (*trail, predicate))
            if any(tokens[i]["dep"] == "neg" for i in children[parent]):
                reasons = [*reasons, "ambiguous_inherited_negation_scope"]
            return inherited, reasons
        if len(subs) != 1:
            return None, ["missing_or_multiple_subjects"]
        index = subs[0]
        if tokens[index]["lemma"] in {"who", "which", "that"} and tokens[predicate]["dep"] == "relcl":
            index = tokens[predicate]["head"]
        t = tokens[index]
        ids = descendants(index, nominal=True)
        modifiers = [{"dependency": tokens[i]["dep"], "phrase": phrase(i, tokens[i]["dep"])}
                     for i in children[index] if tokens[i]["dep"] not in {"det", "punct"}]
        wh = query and (t["lemma"] in {"who", "what"} or any(
            tokens[i]["lemma"] in {"which", "what"} and tokens[i]["dep"] == "det"
            for i in children[index]))
        coordinated = any(tokens[i]["dep"] == "conj" for i in children[index])
        unresolved = (t["pos"] == "PRON" and not wh) or coordinated or t["pos"] not in {"NOUN", "PROPN", "PRON"}
        name_ids = sorted([index, *[i for i in children[index] if tokens[i]["dep"] in {"compound", "flat"}]])
        key = f"mention:{t['start']}"
        if wh:
            key = f"variable:{index}"
        elif t["pos"] == "PROPN" and not coordinated and not any(tokens[i]["dep"] == "poss" for i in children[index]):
            key = "name:" + " ".join(tokens[i]["lemma"] for i in name_ids)
        elif t["pos"] == "PROPN":
            unresolved = True
        types = [noun_type(index)] if t["pos"] == "NOUN" and not coordinated else []
        types.extend(noun_type(i) for i in children[index]
                     if tokens[i]["dep"] == "appos" and tokens[i]["pos"] == "NOUN"
                     and not any(tokens[j]["pos"] in {"VERB", "AUX"} for j in descendants(i)))
        reasons = []
        if coordinated:
            reasons.append("coordinated_subject_distribution_unknown")
        if any(tokens[i]["lemma"] in {"no", "neither", "nobody", "none"}
               for i in ids if tokens[i]["dep"] in {"det", "neg", "preconj", "nsubj"}):
            reasons.append("negative_subject_scope")
        if any(tokens[i]["dep"] in NESTED_CLAUSES for i in children[index]):
            reasons.append("qualified_subject_clause_unresolved")
        if t["dep"] != "nsubj" and tokens[predicate]["dep"] != "relcl":
            reasons.append("passive_or_clausal_subject")
        return {"mention_id": f"mention:{t['start']}", "head": t["lemma"], "head_pos": t["pos"],
                "span": span(ids), "evidence_offsets": evidence(ids), "modifiers": modifiers,
                "type_evidence": types, "identity_status": "unresolved" if unresolved else "query_variable" if wh else "explicit",
                "binding_key": None if unresolved else key,
                "resolution": "unresolved; no antecedent guessed" if unresolved else "explicit grammatical mention"}, reasons

    _, unsafe_quotes = _unsafe_quote_sentences(tokens)
    predicates = [t["i"] for t in tokens if t["pos"] in {"VERB", "AUX"}
                  and t["dep"] not in {"aux", "auxpass", "cop"}]
    facts, issues, identities = [], [], {}
    for index in predicates:
        t, local = tokens[index], children[index]
        owner, reasons = subject(index)
        if owner is None:
            owner = {"mention_id": f"missing:{t['start']}", "head": None, "head_pos": None,
                     "span": None, "evidence_offsets": [], "modifiers": [], "type_evidence": [],
                     "identity_status": "unresolved", "binding_key": None,
                     "resolution": "no grammatical subject identified"}
        identities[owner["mention_id"]] = owner
        if t["sentence_id"] in unsafe_quotes:
            reasons.append("quoted_statement_scope")
        ancestors, parent = [], index
        while parent not in ancestors:
            ancestors.append(parent)
            if tokens[parent]["head"] == parent:
                break
            parent = tokens[parent]["head"]
        if any(tokens[i]["dep"] in {"ccomp", "xcomp", "advcl", "acl"} for i in ancestors):
            reasons.append("embedded_clause_scope")
        # A conjunct can remain under the scope of its governing conditional/report.
        # Preserve it as uncertain rather than treating its absent local marker as proof.
        if any(tokens[a]["pos"] in {"VERB", "AUX"}
               and any(tokens[i]["dep"] in {"ccomp", "xcomp", "advcl", "acl"} for i in children[a])
               for a in ancestors[1:]):
            reasons.append("governing_clause_scope_unresolved")
        if any(tokens[i]["dep"] in NESTED_CLAUSES - {"relcl"} for i in local):
            reasons.append("clause_complement_unresolved")
        if any(tokens[i]["dep"] == "auxpass" for i in local):
            reasons.append("passive_roles_unresolved")
        scope_ids = descendants(index)
        if any(tokens[i]["lemma"] in {"if", "unless", "whether", "or", "either", "neither"}
               for i in scope_ids if tokens[i]["dep"] in {"mark", "cc", "preconj"}):
            reasons.append("condition_or_disjunction_scope")
        negations = [i for i in local if tokens[i]["dep"] == "neg" or tokens[i]["lemma"] == "never"]
        if len(negations) > 1 or (negations and any(tokens[i]["lemma"] == "only" for i in local)):
            reasons.append("complex_negation_scope")
        aux = [i for i in local if tokens[i]["dep"] == "aux"]
        if t["dep"] == "conj" and t["tag"] == "VB" and not aux and not any(tokens[i]["dep"] in SUBJECT_DEPS for i in local):
            aux = [i for i in children[t["head"]] if tokens[i]["dep"] == "aux" and tokens[i]["lemma"] in MODALS]
        args = []
        for i in local:
            dep = tokens[i]["dep"]
            if dep in ARG_DEPS or (dep == "advmod" and i not in negations):
                role = "object" if dep in {"obj", "dobj"} else "complement" if t["lemma"] == "be" and dep in {"attr", "acomp", "oprd"} else dep
                arg = phrase(i, role)
                args.append(arg)
                if any(tokens[j]["dep"] in NESTED_CLAUSES or tokens[j]["pos"] in {"VERB", "AUX"}
                       for j in descendants(i)):
                    reasons.append("argument_clause_unresolved")
                if tokens[i]["pos"] == "PRON":
                    reasons.append("argument_identity_unresolved")
                if arg["scope"]:
                    reasons.append("argument_scope_unresolved")
        if t["lemma"] == "be" and not args:
            reasons.append("missing_copular_complement")
        if query and owner["identity_status"] == "unresolved":
            reasons.append("query_subject_unresolved")
        reasons = list(dict.fromkeys(reasons))
        owner_offsets = {e["start"] for e in owner["evidence_offsets"]}
        evidence_ids = sorted(set(scope_ids + aux + [i for i, token in enumerate(tokens)
                                                    if token["start"] in owner_offsets]))
        # Each record carries its full clause span as well as structured token evidence.
        record = {"fact_id": f"event:{t['start']}", "kind": "event", "subject": owner,
                  "subject_key": owner["binding_key"] or f"unbound:event:{t['start']}",
                  "predicate": t["lemma"], "arguments": args,
                  "polarity": "negative" if negations else "positive",
                  "modality": [tokens[i]["lemma"] for i in aux if tokens[i]["lemma"] in MODALS],
                  "sentence_id": t["sentence_id"], "voice": "passive" if any(tokens[i]["dep"] == "auxpass" for i in local) else "active",
                  "scope_issues": reasons, "assertion_status": "uncertain" if reasons else "asserted",
                  "extraction_status": "uncertain" if reasons else "usable",
                  "evidence_span": span(evidence_ids), "evidence_offsets": evidence(evidence_ids),
                  "derived_from": "predicate"}
        # Explicit copular nominal predicates and nominal subject evidence use one type
        # representation, on both sides of the comparison. No fabricated body sentence.
        if t["lemma"] == "be" and len(args) == 1 and args[0]["role"] == "complement":
            complement = next((i for i in local if tokens[i]["dep"] in {"attr", "acomp", "oprd"}), None)
            if complement is not None and tokens[complement]["pos"] == "NOUN":
                record["kind"] = "type"
        facts.append(record)
        for position, type_arg in enumerate(owner["type_evidence"]):
            facts.append({**record, "fact_id": f"type:{owner['mention_id']}:{position}:{index}",
                          "kind": "type", "predicate": "be", "arguments": [type_arg],
                          "polarity": "positive", "modality": [], "voice": "active",
                          "evidence_span": owner["span"], "evidence_offsets": owner["evidence_offsets"],
                          "derived_from": "nominal_subject_type"})
        issues.extend({"reason": reason, "token_index": index, "offset": t["start"],
                       "evidence_span": span(scope_ids)} for reason in reasons)
        if owner["identity_status"] == "unresolved":
            issues.append({"reason": "subject_identity_unresolved", "token_index": index,
                           "offset": t["start"], "evidence_span": owner["span"]})
    if not predicates:
        issues.append({"reason": "no_predicate", "token_index": None, "offset": None,
                       "evidence_span": {"start": 0, "end": len(text), "quote": text}})
    base = {"text_sha256": text_hash(text), "rules_version": RECORD_RULE_VERSION,
            "record_schema": RECORD_SCHEMA, "subject_mentions": list(identities.values()),
            "issues": issues, "unresolved_restrictions": issues}
    if query:
        conditions, seen = [], set()
        for record in facts:
            signature = (record["kind"], record["subject_key"], record["predicate"], record["polarity"],
                         tuple(record["modality"]), tuple((a["role"], a["head"], tuple(
                             (m["dependency"], m["head_lemma"], m["lemma"]) for m in a["modifiers"])) for a in record["arguments"]))
            if signature not in seen:
                seen.add(signature)
                conditions.append(record)
        if len({t["sentence_id"] for t in tokens}) != 1:
            issues.append({"reason": "multi_sentence_query", "token_index": None, "offset": None})
        if len({r["subject_key"] for r in conditions}) != 1:
            issues.append({"reason": "no_single_shared_query_subject", "token_index": None, "offset": None})
        if not conditions:
            issues.append({"reason": "no_conditions", "token_index": None, "offset": None})
        return {**base, "conditions": conditions, "condition_count": len(conditions),
                "query_structure_supported": bool(conditions) and not issues,
                "explicit_subject_constraint": any(r["subject_key"].startswith("name:") for r in conditions),
                "status": "unsupported" if issues else "supported"}
    incomplete = bool(issues) or not facts
    return {**base, "facts": facts, "extraction_incomplete": incomplete,
            "status": "incomplete" if incomplete else "complete"}
