# Runbook naprawy metadanych adapterow Academy

## Cel

Dostarczyc procedure operacyjna dla historycznych adapterow, ktore nie przechodza deployu z powodu brakujacych lub niespojnych metadanych `base_model`.

## Objawy

Typowe `reason_code` podczas aktywacji/deployu:

1. `ADAPTER_BASE_MODEL_UNKNOWN`
2. `ADAPTER_METADATA_INCONSISTENT`
3. `ADAPTER_BASE_MODEL_MISMATCH`

## Audit preflight

Uruchom audit przed deployem:

```bash
curl -s "http://localhost:8000/api/v1/academy/adapters/audit?runtime_id=ollama&model_id=<runtime_model>"
```

Oczekiwane kategorie:

1. `compatible`
2. `blocked_unknown_base`
3. `blocked_mismatch`

## Minimalny kontrakt metadanych

Aby odblokowac deploy, adapter powinien miec jeden spojny model bazowy w artefaktach:

1. `<adapter_dir>/metadata.json` z polem `base_model`
2. Opcjonalnie (zalecane): `<adapter_dir>/adapter/adapter_config.json` z `base_model_name_or_path`
3. Opcjonalnie: `<adapter_dir>/runtime_vllm/venom_runtime_vllm.json` z `base_model`

## Procedura recznej naprawy

1. Zidentyfikuj adapter z auditu (`adapter_id`, `sources`, `reason_code`).
2. Ustal rzeczywisty model bazowy treningu z logow lub rejestru modeli.
3. Zaktualizuj `metadata.json`, aby `base_model` odpowiadal rzeczywistemu modelowi bazowemu.
4. Jesli istnieje `adapter_config.json`, ustaw zgodne `base_model_name_or_path`.
5. Usun konfliktujace stare manifesty, jesli nie da sie ich uzgodnic.
6. Uruchom ponownie `/api/v1/academy/adapters/audit`.
7. Deploy wykonuj tylko, gdy kategoria to `compatible`.

## Checklista walidacyjna

1. Kategoria auditu to `compatible`.
2. `reason_code` jest pusty.
3. Kanoniczny model runtime zgadza sie z kanoniczna baza adaptera.
4. Wywolanie aktywacji zwraca sukces.

## Uwagi

1. System celowo blokuje niepewne deploymenty (strict metadata confidence), aby unikac cichych, blednych nakladek runtime.
2. Sam fallback do domyslnego modelu z konfiguracji nie jest traktowany jako zaufany dowod dla bezpiecznego deployu.
