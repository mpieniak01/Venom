# Pre-prod Access and Audit Policy

## Goal
Ensure controlled access and auditable operational changes on `preprod`.

## Roles
- Operator: deploy, restart, monitoring.
- QA/UAT: manual acceptance testing and issue reporting.
- Developer: diagnostics/fixes approved in change window.
- Release owner: GO/NO-GO decision.

## Access Rules
1. No shared accounts.
2. Least-privilege access only.
3. Time-boxed elevated access for risky operations.
4. All admin operations must be auditable.

## Mandatory Audit Operations
- `preprod` config changes.
- `ALLOW_DATA_MUTATION=1` override.
- Restore and cleanup operations.
- Manual edits in `preprod` namespaces.

## Audit Record Format
- Actor
- UTC timestamp
- Action
- Ticket/incident ID
- Result

Automation:
- Script: `scripts/preprod/audit_log.sh`
- Make wrapper:
```bash
make preprod-audit ACTOR=<id> ACTION=<operation> TICKET=<id> RESULT=<OK|FAIL>
```
- Output file: `logs/preprod_audit.log`

## Access Review Cadence
- Permission review every 30 days.
- Immediate revoke after role change/offboarding.
- Exception register with expiration date.
