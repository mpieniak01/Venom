# Release Checklist: dev -> preprod -> prod

## Phase 1: Promotion to preprod
- [ ] Changes merged into release branch.
- [ ] Build + deploy to `preprod` successful.
- [ ] Preprod config validated:
  - [ ] `ENVIRONMENT_ROLE=preprod`
  - [ ] `DB_SCHEMA=preprod`
  - [ ] `CACHE_NAMESPACE=preprod`
  - [ ] `QUEUE_NAMESPACE=preprod`
  - [ ] `STORAGE_PREFIX=preprod`
  - [ ] `ALLOW_DATA_MUTATION=0`
- [ ] CI job `Preprod readonly smoke` passed.
- [ ] Manual smoke re-check passed:
```bash
make test-preprod-readonly-smoke
```

## Phase 2: UAT on preprod
- [ ] Critical UAT scenarios executed.
- [ ] All critical scenarios have status PASS.
- [ ] Blocking defects closed.
- [ ] UAT report signed by owner.

## Phase 3: Gate before prod
- [ ] Current `preprod` backup exists.
- [ ] Rollback plan approved.
- [ ] Release window approved.
- [ ] Release owner confirms GO.

## Phase 4: Production deploy
- [ ] Production deploy completed successfully.
- [ ] Production smoke tests PASS.
- [ ] Monitoring and alerts show no critical deviations.

## Phase 5: Post-release
- [ ] Stability check after 30 minutes.
- [ ] Release ticket closed.
- [ ] Audit log updated:
```bash
make preprod-audit ACTOR=<id> ACTION=release TICKET=<release-id> RESULT=OK
```

## Release Decision
- GO / NO-GO:
- Date/time:
- Owner:
- Notes:
