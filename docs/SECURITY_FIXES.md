# Security fixes and dependency hygiene

Plik dokumentuje zmiany i decyzje dotyczące bezpieczeństwa oraz higieny
zależności (aktualizacje wersji, akceptacja ryzyk, ograniczenia projektu).
Ma charakter notatki utrzymaniowej dla projektu eksperymentalnego.

## Ostatnie działania (18.01.2025)

Na podstawie sygnałów z narzędzia **Snyk** podniesiono wersje zależności
zidentyfikowanych jako podatne (CVE – high):

- `aiohttp>=3.13.3` – throttling i limity zasobów
- `urllib3>=2.6.3` – obsługa skompresowanych danych
- `transformers>=4.57.6` – potencjalna deserializacja niezweryfikowanych danych
- `azure-core>=1.38.0` – potencjalna deserializacja niezweryfikowanych danych
- `pydantic` podniesiono do `>=2.12,<3.0` w celu zachowania zgodności z vLLM 0.12.x
  oraz eliminacji konfliktu wersji (warning runtime).

## Narzędzia i zakres kontroli

- **Snyk**
  Wykorzystywany manualnie do analizy podatności w zależnościach.
  Nie jest zintegrowany z pipeline CI.

- **pre-commit + Ruff**
  Stosowane do kontroli jakości i spójności kodu.
  Nie obejmują skanowania zależności pod kątem CVE.

- **GitHub Security (Dependabot / GitGuardian)**
  Wykorzystywane są domyślne mechanizmy GitHuba:
  - alerty zależności,
  - skanowanie sekretów.
  Nie stanowi to pełnego systemu audytu bezpieczeństwa.

### Polityka wersji zależności (Python)

- `semantic-kernel >= 1.39.1` – działa z `pydantic 2.12.x` przy shimsie `Url` (dodany w `venom_core/__init__.py`).
- `pydantic 2.12.x` – wymagany przez vLLM 0.12.x (pip zgłasza warning, bo SK deklaruje `<2.12`, ale działa z shims).
- Oczekiwane jest utrzymywanie zestawu: SK 1.39.1+, Pydantic 2.12.x, vLLM 0.12.x; w razie podbicia którejkolwiek paczki należy zweryfikować importy SK (Url) i uruchomić smoke testy.

Projekt obecnie **nie posiada**:
- SonarQube / SonarCloud,
- cyklicznego skanera CVE w CI,
- automatycznej weryfikacji artefaktów modelowych.

## Uwagi dotyczące ryzyk

- W ekosystemie HuggingFace (`transformers`, `accelerate`, `tokenizers`)
  występują zgłoszenia typu *deserialization of untrusted data*, dla których
  brak pełnych upstream fixów.

- Ryzyko ograniczane jest organizacyjnie:
  - używane są wyłącznie zaufane modele i artefakty,
  - brak dynamicznego pobierania modeli w runtime.

## Rejestr ryzyk

- **Źródło modeli i artefaktów**
  Venom jest oprogramowaniem eksperymentalnym.
  System nie weryfikuje automatycznie integralności ani pochodzenia modeli.
  Odpowiedzialność za wybór źródeł spoczywa na użytkowniku.
