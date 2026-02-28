# Checklista release: dev -> preprod -> prod

## Faza 1: Wejście na preprod
- [ ] Deploy na `preprod` zakończony sukcesem.
- [ ] Konfiguracja preprod zgodna z guardami.
- [ ] CI `Preprod readonly smoke` na zielono.
- [ ] Smoke manualny:
```bash
make test-preprod-readonly-smoke
```

## Faza 2: UAT
- [ ] Scenariusze krytyczne wykonane.
- [ ] Status krytycznych scenariuszy: PASS.
- [ ] Brak defektów blokujących.
- [ ] Raport UAT podpisany.

## Faza 3: Bramka przed prod
- [ ] Aktualny backup `preprod` istnieje.
- [ ] Plan rollback zatwierdzony.
- [ ] Okno release zatwierdzone.
- [ ] Decyzja ownera: GO.

## Faza 4: Po release
- [ ] Stabilność po 30 min potwierdzona.
- [ ] Ticket release zamknięty.
- [ ] Audyt uzupełniony:
```bash
make preprod-audit ACTOR=<id> ACTION=release TICKET=<release-id> RESULT=OK
```
