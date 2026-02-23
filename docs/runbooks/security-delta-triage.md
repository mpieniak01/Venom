# Security Delta Triage (Operational)

This runbook defines who, when, and how to triage dependency security delta from:
- `make security-delta-scan`
- nightly workflow: `.github/workflows/security-delta-nightly.yml`

## 1. Ownership

1. Primary owner: repository maintainers responsible for dependency updates.
2. Backup owner: on-duty engineering maintainer for release stability.

## 2. Triage Cadence

1. Nightly scan: every day (artifact `security-delta-latest.json`).
2. Manual scan: before release and after any major dependency bump.
3. Incident mode: run immediately after new public CVE affecting runtime stack.

## 3. Classification Rules

1. `critical` or `high` in production dependencies:
   - classify as `P1`,
   - open scoped security PR immediately.
2. `moderate` in production dependencies:
   - classify as `P2`,
   - patch in nearest planned maintenance window.
3. `low`/`info`:
   - classify as `P3`,
   - monitor and patch opportunistically.
4. Dev-only findings:
   - classify separately from runtime risk,
   - patch when safe for CI/tooling.

## 4. SLA Targets

1. `P1` (`critical/high`, prod): triage in 24h, fix/mitigate in 72h.
2. `P2` (`moderate`, prod): triage in 3 business days, fix in 14 days.
3. `P3` (`low/info` or dev-only): triage in 14 days, fix in next regular dependency cycle.

## 5. Decision Flow

1. Reproduce with local command:
```bash
make security-delta-scan
```
2. Confirm scope (prod vs dev-only, transitive vs direct).
3. Validate fix candidate with dry-run resolver if needed.
4. Implement minimal scoped bump.
5. Re-run:
   - `make security-delta-scan`
   - mandatory release gates before merge/push.

## 6. Report Template (for 170 backlog update)

1. Date/time of scan.
2. Delta summary (`python`, `web`, severity split).
3. Classification (`zamkniete / do realizacji / do monitoringu`).
4. SLA class (`P1/P2/P3`) and owner.
5. PR link or mitigation note.
