# Robust Fusion R2 automatic measurement execution v1

Status: `POST_SOURCE_LOCK_IMPLEMENTATION_SPEC_AWAITING_SEAL`

This executor is the preregistered R2 measurement's missing post-source-lock implementation. It changes no scientific definition. Its only inputs are the formal v7/v7.1 source-data lock, the previously sealed R2 measurement preregistration, and the already qualified local encoder snapshots.

The main encoder is `intfloat/multilingual-e5-base@d128750597153bb5987e10b1c3493a34e5a4502a`; the sensitivity encoder is `sentence-transformers/distiluse-base-multilingual-cased-v2@bfe45d0732ca50787611c0fe107ba278c7f3f889`. Roles cannot be exchanged. The existing qualified implementation fixes CPU execution, one Torch thread, deterministic algorithms, right truncation, the frozen tokenizer/model revisions, E5 `query:` input prefix, normalized embeddings, float32 stored vectors, and float64 cosine accumulation. Each of 128 families contributes one reference and two candidates. The estimand for each candidate is the maximum cosine to its unique target-equivalent Clean reference set; here that set has exactly one locked reference. Query-to-candidate similarity is never computed.

The executor may run only once. It must verify all preparation and source-lock hashes, refuse any existing automatic or human-package output, encode all 384 locked texts with both encoders without score-based replacement or deletion, persist vectors, per-input token/truncation metadata, vector hashes, exact encoder provenance, candidate scores, and manifests, and then produce four physically separated blind packages: relation A/B and similarity A/B. Each package has 256 rows. The two packages assigned to one researcher therefore total 512 rows.

Human packages expose only opaque audit IDs, query, reference, candidate, task instructions, and blank submission fields. They must not expose source/generator identity, construction role, candidate role/suffix, encoder score, rank, caliper, condition cell, similarity band, answer key, or expected direction. Relation submissions independently record reference validity, unique-target-group validity, relation (`equivalent` or `factual_conflict`), conflict type when applicable, uncertainty, and notes. Similarity submissions independently use the frozen seven-point behaviorally anchored scale. A facilitator-only registry maps opaque audit IDs to locked candidate IDs and is never distributed as an annotator package.

Model outputs and construction provenance are not truth. No measurement finalizer, readiness, Gate, Blind, reranker-effect, D1–D3, A0, or M1 entry may run before two independent researchers complete all four packages and their submissions are locked before comparison.

