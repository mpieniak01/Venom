# Pre-prod Backup and Restore (Shared Stack)

## Goal
Provide repeatable backup and restore for `preprod` data while `dev` and `preprod` share one technical stack.

## Data Scope
- Memory data: `./data/memory/preprod`
- Training data: `./data/training/preprod`
- Timelines: `./data/timelines/preprod`
- Synthetic training data: `./data/synthetic_training/preprod`
- Workspace data: `./workspace/preprod`
- Redis namespace: `preprod:*`

## Automation Artifacts
- Script: `scripts/preprod/backup_restore.sh`
- Make targets:
  - `make preprod-backup`
  - `make preprod-restore TS=<timestamp>`
  - `make preprod-verify TS=<timestamp>`
  - `make preprod-audit ACTOR=<id> ACTION=<name> TICKET=<id> RESULT=<status>`

## Backup Schedule
- Daily backup: `02:00`
- Weekly full verification: Sunday `03:00`
- Daily retention: 14 days
- Weekly retention: 8 weeks

## Backup Procedure
1. Verify guard config:
- `ENVIRONMENT_ROLE=preprod`
- `ALLOW_DATA_MUTATION=0`
2. Run backup:
```bash
make preprod-backup
```
3. Save returned timestamp (`Backup timestamp: ...`) in release/audit records.
4. Record event in audit log:
```bash
make preprod-audit ACTOR=<operator> ACTION=backup TICKET=<change-id> RESULT=OK
```

## Controlled Restore Procedure
1. Open a change window and obtain owner approval.
2. Enable temporary mutation override only for restore operation:
```bash
make preprod-restore TS=<timestamp>
```
3. Verify backup integrity and run read-only smoke:
```bash
make preprod-verify TS=<timestamp>
```
4. Record restore event in audit log:
```bash
make preprod-audit ACTOR=<operator> ACTION=restore TICKET=<incident-id> RESULT=OK
```

## Monthly Restore Drill
- Restore latest backup in controlled environment or approved maintenance window.
- Confirm integrity and smoke-readonly pass.
- Record RPO and RTO values in operations notes.

## Acceptance Criteria
- At least one successful daily backup.
- At least one documented monthly restore verification.
- `make preprod-verify TS=<timestamp>` passes.
