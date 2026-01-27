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
- `pydantic` podniesiono do `>=2.12,<3.0` zgodnie z polityką „nowszych wersji”.
- `openai` podniesiono do `>=2.8.0` (wymaganie `litellm>=1.81.3`).
- `openapi-core` podniesiono do `>=0.22.0`, aby odblokować `werkzeug>=3.1.5`.
- `graphrag` i `lancedb` przypięte do stabilnych wersji w `requirements.txt`
  (ograniczenie backtrackingu resolvera).

## Status po ostatnim skanie (bieżące)

- Podbicie `pypdf`, `filelock`, `litellm`, `marshmallow`, `pyasn1` i `werkzeug`
  zmniejsza liczbę podatności, ale **łamie** zależności:
  - `semantic-kernel` deklaruje `openai<2` i `pydantic<2.12` (wymaga weryfikacji
    i ewentualnych patchy/override przy nowszych wersjach).
  - `semantic-kernel` oczekuje `openapi-core<0.20`, podczas gdy projekt używa `>=0.22`.
  Przyjęto decyzję: **idziemy w nowsze wersje mimo konfliktów** – wymagane testy
  regresji oraz ewentualne poprawki runtime.

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

- `semantic-kernel >= 1.39.2` – deklaruje `pydantic <2.12` i `openai<2`, ale projekt
  utrzymuje nowsze wersje wbrew metadanym. Wymaga walidacji runtime.
- `pydantic >=2.12,<3.0` – docelowy zakres zgodny z polityką aktualizacji.
- Oczekiwane jest utrzymywanie zestawu: SK 1.39.2+, Pydantic 2.12+ (z override),
  OpenAI 2.x. Po każdej aktualizacji konieczne smoke testy.

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
