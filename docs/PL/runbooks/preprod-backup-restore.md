# Backup i restore preprod (wspólny stack)

## Cel
Powtarzalny backup i odtworzenie danych `preprod` w modelu wspólnego stacka.

## Zakres danych
- `./data/memory/preprod`
- `./data/training/preprod`
- `./data/timelines/preprod`
- `./data/synthetic_training/preprod`
- `./workspace/preprod`
- Redis namespace `preprod:*`

## Artefakty automatyzacji
- Skrypt: `scripts/preprod/backup_restore.sh`
- Komendy:
  - `make preprod-backup`
  - `make preprod-restore TS=<timestamp>`
  - `make preprod-verify TS=<timestamp>`
  - `make preprod-audit ACTOR=<id> ACTION=<name> TICKET=<id> RESULT=<status>`

## Procedura backup
1. Potwierdź:
- `ENVIRONMENT_ROLE=preprod`
- `ALLOW_DATA_MUTATION=0`
2. Uruchom:
```bash
make preprod-backup
```
3. Zapisz timestamp backupu i dodaj wpis audytowy:
```bash
make preprod-audit ACTOR=<operator> ACTION=backup TICKET=<change-id> RESULT=OK
```

## Procedura restore (kontrolowana)
1. Otwórz okno zmian i uzyskaj akceptację ownera.
2. Uruchom restore:
```bash
make preprod-restore TS=<timestamp>
```
3. Zweryfikuj integralność i smoke:
```bash
make preprod-verify TS=<timestamp>
```
4. Dodaj wpis audytowy:
```bash
make preprod-audit ACTOR=<operator> ACTION=restore TICKET=<incident-id> RESULT=OK
```
