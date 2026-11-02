# Independent training milestones

A plan describes explicit actions; it never rents a host, starts GPU work, advances
another step, activates an adapter or deletes resources. Prepare a single input
bundle with `--updates 160 --max-seconds 7200`, then reuse its fixed identity for
all steps. The default reviewed plan is 80 → 125 → 160. Other strictly increasing
plans up to 256 total updates are supported. Native stages remain at most 128
updates; the training engine and its existing checkpoint fingerprint are unchanged.

```bash
python -m venom_core.services.remote_training.cli plan \
  --run-id granite-g03-milestones --milestones 80 125 160 \
  --max-seconds 7200 --output data/training/g03-campaign/plan.json
```

Packaging, host initialization, upload and smoke keep their existing separate
commands. Use an already configured SSH alias with verified host keys. In the
following examples, add the same `--ssh-config`, `--remote-root` and
`--remote-python` options required by that host **before** the action.

```bash
python -m venom_core.services.remote_training.cli --host gpu start \
  --run-id granite-g03-milestones --stage smoke
python -m venom_core.services.remote_training.cli --host gpu start \
  --run-id granite-g03-milestones --stage train --until-update 80
python -m venom_core.services.remote_training.cli --host gpu watch \
  --run-id granite-g03-milestones
python -m venom_core.services.remote_training.cli --host gpu attempts \
  --run-id granite-g03-milestones
```

Read `attempt`, `completed_updates`, `result_checkpoint`, `status` and `exit_code`
from the terminal attempt history. Attempt numbers are assigned at runtime and
must not be guessed: retries and failed starts consume numbers.

```bash
python -m venom_core.services.remote_training.cli --host gpu collect \
  --run-id granite-g03-milestones --attempt <ATTEMPT_80> \
  --include-checkpoint --output /absolute/results/candidate-80.zip
python -m venom_core.services.remote_training.cli --host gpu resume \
  --run-id granite-g03-milestones \
  --checkpoint attempts/<PADDED_ATTEMPT_80>/result/checkpoint --until-update 125
```

Collect/inspect/import/evaluate the 125 candidate separately, then explicitly
resume its `result_checkpoint` with `--until-update 160`. `inspect-result` and
`import-result` still require the original input bundle. Fresh local GPU reload
remains separate. Each comparison uses a separate output directory and expected
adapter SHA-256. The fixed input/profile/code/host qualification cannot be silently
changed between milestones. Optimizer/RNG continuation remains host-bound.

## Failure boundaries

- Each milestone is a separate attempt with its own worker, logs, normalized result
  and complete native checkpoint. No mutable `latest` adapter is used as evidence.
- `succeeded` means that attempt reached its requested target, not that the entire
  plan ran. Progress exposes both `total_updates` for this target and
  `planned_max_updates` for the input budget.
- Terminal outcomes are atomically sealed and directory-fsynced. Seals bind artifact
  hashes. Recovery recognizes a completed seal after supervisor state loss; damaged
  evidence is not promoted to success.
- Start/resume retries with the same target and parent checkpoint are idempotent.
  Failed-step resume retains that step's target when it is omitted. Changing an
  active request's target is rejected.
- Earlier results remain independently collectible by `--attempt`, even while the
  next attempt is active or failed. A partial transfer resumes at the same offset;
  a changed candidate/identity cannot be mixed into that transfer.
- `retry` is an explicit fresh attempt, not a continuation. For expensive partial
  work use `resume` with a verified checkpoint. Neither command replenishes the
  frozen cumulative time budget. Idle time between steps is not worker time.
- Each terminal stage releases GPU ownership. Other uses are then possible.
  Collection is read-only and can overlap later training. Model evaluation on the
  same GPU must acquire ownership; it does not run alongside training implicitly.
- Stop, failure and completion retain the host and completed artifacts. A new host
  requires qualification; an archived optimizer is not portable resume authority.

## Dialogue evaluation is another independent step

```bash
python -m scripts.granite_operator.dialogue_cases \
  --material /absolute/G03-material --output /absolute/new-dialogue-benchmark
```

The freezer checks the audited material inventory and publishes the manifest only
after a complete staged copy. Repeating the same successful freeze verifies and
reuses it; a failed publication does not change training data. Use its manifest
with `scripts.granite_operator.comparison` for any one candidate. Model, tools and
oracles run together on the selected host, with the configured parallel policy.

Frozen `followups` are supplied only after `Finish needs_input`. The oracle checks
that clarification happened when required and that the final answer uses the
provided values. CLI checks allow equivalent quoting, option ordering and
`--option=value`, while rejecting swapped/missing/duplicate/unknown arguments.
No command is executed merely to judge an answer requesting syntax only. Human
reply time is simulated and excluded from interpretation of model task latency.
Prepared G03 held-out templates remain diagnostic, not independent confirmation.
A successful reference replay proves evaluator/data consistency, not model quality.

All provider/GPU runs remain explicit operator actions. Automated tests use local
fake stages and transports; no paid environment is provisioned by this flow.


An unreadable or inconsistent sealed outcome is returned by `attempts` as an
`invalid` entry with its attempt number. Other candidates remain listed and
collectable; the invalid candidate still fails closed during collection.
State and plan publication uses approved data roots and directory-relative
file descriptors, rejecting symlinks even if a child directory is replaced
between validation and writing.

Malformed checkpoint receipts encountered before sealing produce an
`invalid_evidence` outcome. Status and attempt listing remain available,
while collection rejects that candidate and preserves access to older ones.
