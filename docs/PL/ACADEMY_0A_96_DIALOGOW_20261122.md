# 0A wide acceptance — 96 full conversations (2026-11-22)

## Decision

**STOP for both candidate checkpoints.** Neither candidate meets the 0A dev threshold. Do not promote either checkpoint or open the private final/holdout set.

## Panel and execution

- Fresh panel: 96 conversations, 24 in each group S/K/W/R, four turns each (384 turns per arm).
- Panel file SHA-256: 6647deb29098512fe3c25fe37507e8586a6ded4f3b74106413248ea31ceddf93; canonical scorer-panel SHA-256: d33695118d016b21bafdc3b45955250cc7eeaba7701817e6c32fb0e50cf9eca6; rubric SHA-256: 452a35712fcde73bc5daf0b1e46ea236695d5cbb5f23cc5ee891dce7e570636e.
- Freshness checks found no repeated prompts against the prior 0A panels or available train/dev examples.
- Same model family and base snapshot for all arms: LiquidAI/LFM3-Omni-2B, snapshot 0e3f697589bcd9fac2172156a8d50d66ca3efa7e56f5a4e52fe69cadac987319, code revision b030a61d45e79f56936f72f4df8cdc4b5f31e8e0.
- Academy and qualified-chat were OFF; each run retained separate per-dialogue history, pinned the adapter and input hashes, and completed rollback.
- The worktree changed between the P13 and candidate runs only for Academy review/qualification code, API schemas, generated contracts, tests, and documentation; no chat inference/runtime files changed. The P13 report diff_sha256 is the empty-tree hash; candidate reports include those unrelated changes.
- Run output is in train-p13.json, train-seed42.json, and train-seed43.json. All three have exactly 384 turns and passed the assembler's prompt, history, identity, flags, and completion checks.

## Results

| Arm | Adapter | Full conversations | S | K | W | R | P13 full passes retained | Lost P13 passes | Critical turns | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |
| P13 baseline | omni-p13-145 | 4/96 | 0 | 1 | 1 | 2 | — | — | 170 | Baseline |
| seed42 | omni-p13-step21-seed42 | 3/96 | 1 | 1 | 1 | 0 | 2/4 | R-03, R-09 | 167 | STOP |
| seed43 | omni-p13-step21-seed43 | 3/96 | 0 | 1 | 1 | 1 | 2/4 | R-03, R-09 | 169 | STOP |

The candidate gates require at least 72/96 full passes, at least 16/24 in every group, zero critical errors, and retention of every full P13 pass. Both candidates miss the overall and every group threshold, have critical errors, and lose two P13 passes. Each gains one conversation that P13 did not pass, which does not offset the regressions.

P13 is the parent baseline, not a promotion candidate. Its four full passes define the parent-retention set; the candidate gate requires zero critical turns.

## Blind review and provenance

Reviewers saw only arms A/B/C and were assigned 24 conversations each, balanced across S/K/W/R. Five reviewers contributed judgments (four delegated reviewers and Codex root). The deterministic conversation_review.score() scorer then applied the 0A thresholds. Reviewer labels and judgments are self-reported provenance; they are not cryptographically authenticated.

Blind judgment fragments are blind-judgments-1.json through blind-judgments-4.json; the fourth reviewer subset is also preserved as blind-judgments-4b.json. score-payload-reviewed.json contains the completed scorer input and its reproducible results (SHA-256 98b03c35de3ea82ca8f345ae25571d37af7565f6c2fe1c3f0162448215a30c91). comparison-score.json records the alias mapping, model identities, score outputs, and reviewer provenance.

## Academy campaign gate

CampaignSpec.conversation_review now opts a 0A campaign into the checkpoint receipt gate. It binds a receipt to campaign/plan/profile, run and checkpoint step, sealed checkpoint result, P13 and candidate model identities, dataset/protocol, and panel hash. Missing receipt leaves the campaign awaiting_review; STOP or binding/hash mismatch blocks selection. A PASS receipt is rechecked before transition and before final qualification, including tampering after PASS. The 0A campaign example is documented in docs/PL/ACADEMY_EKSPERYMENTY.md.

The gate is opt-in; no live campaign was started or modified for this diagnostic, and no final holdout was opened. A campaign must include conversation_review with the exact canonical panel hash and a receipt ID prefix to enforce this gate.

## Verification

- pytest -q tests/test_academy_conversation_review.py tests/test_training_experiment_campaign.py tests/test_academy_remote_text_evidence.py: **187 passed, 1 warning**.
- make pr-fast: **PASS**; 2,858 tests, 0 failures/errors, 9 skipped; changed-lines coverage 96.99%.
- prepare_review.py --self-test: PASS.
- git diff --check: PASS.

This is a model-only, text-only comparison with Academy OFF. It does not run Studio or external tools; those remain separate end-to-end acceptance scopes.
