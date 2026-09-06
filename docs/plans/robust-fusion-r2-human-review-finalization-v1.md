# Robust Fusion R2 human review and finalization executor v1

> executor_id: `ROBUST-FUSION-R2-HUMAN-REVIEW-FINALIZATION-2026-08-29-v1`
> nature: post-submission-lock implementation of the already sealed protocol
> scientific protocol changed: no

This executor fills an implementation gap discovered only after all four real researcher
submissions had been locked by raw-byte SHA-256. It does not change the R2 preregistration,
estimand, fixed 128-family/256-candidate denominator, encoder roles, conditional
standardization, caliper, bootstrap, thresholds, or unique stopping rule.

Before parsing any answer, the preparation command must bind the four immutable submission
hashes, byte sizes and paths; their four package manifests; the blind registry; the formal
source-data lock; the automatic manifest; and the sealed R2 preregistration. It snapshots this
specification, implementation, CLI and synthetic tests. Existing preparation, review,
adjudication or finalization outputs are never overwritten.

Validation is fail-closed. Every package must retain its exact manifest, task/reviewer identity,
header, 256-row denominator, audit-ID set and physical A/B separation. Relation values are
limited to the frozen enums and conditional conflict-type rule. Similarity is an integer 1–7.
Any missing, duplicate, extra, malformed or whitespace-normalized value is rejected without
editing the researcher submission. `uncertain=yes` requires a note.

The blind facilitator registry is used only to align opaque A/B audit IDs to the same candidate.
It is not an answer key. Relation comparison uses `valid_reference`, `unique_target_group`,
`target_relation` and `conflict_type`; any field difference or either `uncertain=yes` requires
human adjudication. Similarity requires human adjudication for any ordinal difference or either
`uncertain=yes`. The executor may report disagreement by frozen design strata, but source
construction roles never determine a final relation or similarity value.

When any adjudication item exists, the executor writes only a physically isolated facilitator
package containing the disputed text and the two locked human values, with no model score,
generator identity, construction role, answer key or expected direction. Codex and automated
tools must not fill the adjudication submission.

Zero-adjudication finalization is permitted only when all four locked submissions remain
byte-identical, all package and preparation hashes remain unchanged, every candidate has one
relation and similarity value from each reviewer, all three adjudication sets are empty, all
`uncertain` values are `no`, and the two researchers agree exactly. Final human records retain
provenance to both locked audit IDs and both identical submitted values. The finalizer does not
read a source construction role.

The formal finalizer then runs exactly once with the preregistered seed `2026082911`, 9,999
family-clustered stratified bootstrap iterations, fixed denominator 256 and missing-as-failure.
It reports pre-adjudication similarity QWK/within-one, conditional E5 validity, caliper,
resolution, common support and all other frozen gates. DistilUSE remains a sensitivity-only
report and cannot create an alternative PASS. Only the existing
`R2_MEASUREMENT_PASS_AWAITING_READINESS` result authorizes a separate outcome-blind readiness
review; FAIL/INCONCLUSIVE is terminal with no supplement or rerun.

This executor never runs readiness, Gate A/B, Blind, reranker effects, D1–D3, A0 or M1.
