# Robust Fusion R2 source authorship v7 (Codex direct authorship)

Protocol ID: `ROBUST-FUSION-R2-SOURCE-CODEX-AUTHORED-2026-08-29-v7`

Status before seal: `RESULT_BEFORE_AUTHORSHIP_PROTOCOL_PENDING_LOCAL_SEAL`

## Authorization and scope

The research lead user authorized this path after source-recovery v6 ended, using the exact statement: “如果你反复尝试DeepSeek还是觉得不够好，就由你自己替代完成某些任务，现在你不要管这个要求，先继续至V6结束”. The delegating task is `01a046dd-168d-7151-abb2-d88697fdaadd`; the executing Codex task is `01a04c5a-d07c-7db3-8641-3bc092ecad51`. The runtime model identity is not exposed authoritatively, so the frozen value is `unavailable_not_inferred`.

This is a source-proposal implementation path. It is not a change to the R2 scientific preregistration, estimand, fixed denominator, encoder roles, human measurement, measurement thresholds, or any Gate. No DeepSeek or other external generator may be called by v7.

## Immutable inheritance

- All v2–v6 preparation, live, diagnostic, failure, audit, response, and terminal artifacts remain append-only and read-only.
- R2SRC-001 is inherited byte-for-byte from the v4/Flash acceptance through the v6 accepted ledger.
- R2SRC-002 is inherited byte-for-byte from the v6/Pro acceptance.
- Both rows are replayed through the unchanged parser and all mechanical gates, retain their original proposal hashes and generator provenance, are non-replaceable, and precede all v7 rows in cross-slot near-duplicate checks.

## Frozen authorship frame

- The authoritative 128-row slot registry is the previously sealed registry with SHA-256 `c717641388cf0264ff75b17bec4d4b986a32a309fc6dfe8ab7b13ccbafc29f37`.
- R2SRC-003–128 are authored only from each row's frozen synthetic role, language, length stratum, conflict type, and edit level. Dataset roles are synthetic calibration roles, not natural-data claims.
- Chinese short references/candidates contain 35–130 normalized characters; Chinese long contain 160–420. English short contain 18–70 normalized words; English long contain 90–220. Authorship targets the interior ranges already frozen by v4: zh short 60–90 characters, zh long 220–300, en short 30–45 words, en long 120–160 words.
- Normalized Levenshtein distance from reference to both candidates remains level 1 `[0.02,0.18]`, level 2 `[0.08,0.28]`, level 3 `[0.15,0.40]`, and level 4 `[0.22,0.58]`.
- The unchanged conflict types are `numeric`, `version_time`, `negation_direction`, and `applicability_condition`. The conflict candidate changes only the designated factual slot and preserves the rest of the proposition.
- Query, reference, equivalent candidate, and conflict candidate must be pairwise distinct after normalization. The equivalent candidate preserves the entire proposition and changes only non-factual wording or syntax.
- Edit levels increase from local lexical/ordering changes to phrase, clause/syntax, and multi-place non-factual rewrites. Within a family, equivalent and conflict candidates use comparable surface intensity. Across families, entities, predicates, syntax, register, and fictional fact domains are intentionally varied without seeing encoder or human results.

## Forbidden inputs and outputs

The author may not read or reuse failed v2–v6 response bodies, any R1/Blind/production/internal text, encoder scores, human scores, answer keys, or confirmation rankings. The author must not assign relation truth or a 7-point similarity score. A v7 object is only `PROPOSAL_ONLY_AWAITING_INDEPENDENT_HUMAN_REVIEW`.

## Append-only first-pass rule

Each complete draft is stored with its canonical SHA-256 in the append-only attempt ledger before mechanical validation. The unchanged parser then checks schema, identity, language, length, four-way normalized uniqueness, both frozen edit bands, R1 exact/template/5-gram exclusion, and cross-R2 exact/template/5-gram exclusion. The first complete object that passes every mechanical gate is permanently accepted. A failed draft remains in the ledger and may be revised only in response to its enumerated mechanical failure; no text is programmatically rewritten, and no second passing variant may be generated or selected.

R2SRC-003–128 must all pass before any E5/DistilUSE execution or score access. Only then may all 128 rows be locked as the fixed source denominator, followed by exactly one frozen local encoder run and construction of physically separated A/B relation and similarity packages. Human reviewers receive no generator identity, construction role, model score, band, answer key, or expected direction.

## Stop rules

V7 stops fail-closed on inherited evidence drift, parser/preregistration/slot-registry drift, out-of-order or duplicate slot submission, any attempted overwrite/replay, mechanical rejection pending a versioned human-authored revision, or incomplete denominator. Before human submission it may proceed only through source lock, one encoder execution, and blind-package generation. Finalizer, readiness, Gate A/B, Blind, reranker effects, D1–D3, A0, and M1 remain forbidden.
