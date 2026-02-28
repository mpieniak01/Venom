# Dostępy i audyt preprod

## Cel
Kontrola dostępu i ślad audytowy operacji na `preprod`.

## Zasady
1. Brak kont współdzielonych.
2. Least privilege.
3. Czasowe podniesienie uprawnień tylko na okno zmian.
4. Każda operacja administracyjna ma wpis audytowy.

## Operacje obowiązkowo audytowane
- Zmiany konfiguracji `preprod`.
- Override `ALLOW_DATA_MUTATION=1`.
- Restore i cleanup.
- Ręczne ingerencje w namespace `preprod`.

## Narzędzie audytu
- Skrypt: `scripts/preprod/audit_log.sh`
- Komenda:
```bash
make preprod-audit ACTOR=<id> ACTION=<operacja> TICKET=<id> RESULT=<OK|FAIL>
```
- Log: `logs/preprod_audit.log`
