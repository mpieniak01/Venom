# ZADANIE: 029_THE_LAUNCHPAD (Cloud Deployment, Generative Media & Marketing Strategy)

**Priorytet:** Strategiczny (Product Release & Monetization Capability)
**Kontekst:** Warstwa Wdrożeniowa i Kreatywna
**Cel:** Wyposażenie Venoma w zdolność do "wypuszczenia" produktu w świat. System ma potrafić samodzielnie skonfigurować zdalny serwer (VPS/Cloud), wdrożyć tam aplikację (CI/CD), wygenerować dla niej identyfikację wizualną (Logo/Grafiki) oraz przygotować kampanię marketingową.

---

## 1. Kontekst Biznesowy
**Problem:** Venom tworzy aplikacje, które "kurzą się" w katalogu `./workspace`. Nie ma możliwości ich opublikowania, aby byli dostępni dla prawdziwych ludzi w Internecie. Ponadto aplikacje są "nagie" – nie mają logo ani materiałów promocyjnych.
**Rozwiązanie:**
1.  **DevOps Agent:** Loguje się po SSH na zdalny serwer i stawia kontenery.
2.  **Creative Agent:** Używa modeli dyfuzyjnych (Stable Diffusion/DALL-E) do generowania grafik.
3.  **Pipeline "Go-Live":** Jedno polecenie uruchamia proces: Build -> Deploy -> Branding -> Announce.

---

## 2. Zakres Prac (Scope)

### A. Zarządca Chmury (`venom_core/infrastructure/cloud_provisioner.py`)
*Utwórz nowy moduł.* Wrapper na narzędzia `Ansible` lub czyste biblioteki SSH (`fabric` / `asyncssh`).
* **Funkcje:**
    - `provision_server(host, user, key_path)`: Instaluje Dockera i Nginx na czystym Linuxie.
    - `deploy_stack(stack_name, compose_file)`: Przesyła pliki (`rsync`/`scp`) i uruchamia `docker compose up` na zdalnej maszynie.
    - `configure_domain(domain, ip)`: (Opcjonalnie) Konfiguruje DNS (np. Cloudflare API).

### B. Umiejętność Medialna (`venom_core/execution/skills/media_skill.py`)
*Plugin Kreatywny.*
* **Integracja:**
    - **Lokalnie:** Obsługa `Stable Diffusion` (np. przez `AUTOMATIC1111` API lub `diffusers` z ONNX).
    - **Chmura:** OpenAI DALL-E 3 (jeśli skonfigurowano klucz), Narzedzia Gemini generowanie filmow i grafik. Dokumentowanie wizju oraz architektury projektu.
* **Metody (@kernel_function):**
    - `generate_image(prompt: str, size: str, style: str) -> path`: Generuje obraz i zapisuje w `./workspace/assets`.
    - `resize_image(path: str, w: int, h: int)`: Przygotowuje assety do web (favicon, og:image).

### C. Agent Dyrektor Kreatywny (`venom_core/agents/creative_director.py`)
*Nowy agent "Artystyczny".*
* **Rola:** Branding & Marketing.
* **Kompetencje:**
    - Tworzenie promptów do grafik (np. "Minimalist logo for a fintech app, vector style").
    - Pisanie tekstów na Landing Page (Copywriting).
    - Tworzenie treści postów na Social Media (Twitter/LinkedIn).
* **Współpraca:** Zleca `Designerowi` (PR 023), gdzie wstawić wygenerowane obrazki w kodzie HTML.

### D. Agent DevOps (`venom_core/agents/devops.py`)
*Wyspecjalizowany inżynier.*
* **Rola:** Zarządzanie infrastrukturą produkcyjną.
* **Zadania:**
    - Zarządzanie kluczami SSH i sekretami produkcyjnymi (Vault z PR 024 - *jeśli byłby wdrożony, tutaj użyj prostego `.env.prod`*).
    - Monitorowanie zdrowia zdalnych deploymentów.
    - Obsługa certyfikatów SSL (Certbot).

### E. Dashboard: "Mission Control"
* Nowy widok **Deployments**:
    - Mapa serwerów (Live Status).
    - Przycisk "Deploy to Production".
    - Galeria wygenerowanych Assetów (przeglądarka obrazków).

---

## 3. Kryteria Akceptacji (DoD)

1.  ✅ **Zdalne Wdrożenie:**
    * Podajesz Venomowi IP czystego serwera VPS (lub lokalnego VM).
    * Venom instaluje tam Dockera, przesyła aplikację "Sklep" (stworzoną w poprzednich PR) i uruchamia ją.
    * Aplikacja jest dostępna pod publicznym adresem IP.
2.  ✅ **Branding:**
    * Aplikacja ma wygenerowane unikalne logo (plik `.png`) widoczne na pasku nawigacji.
    * W katalogu projektu znajduje się plik `MARKETING_KIT.md` z propozycją tweeta premierowego i opisem produktu.
3.  ✅ **Autonomia:**
    * Venom sam dobiera styl grafik do tematyki aplikacji (np. "Mroczny cyber-punk" dla narzędzia security, "Pastelowy" dla kwiaciarni).

---

## 4. Wskazówki Techniczne
* **SSH:** Użyj biblioteki `asyncssh` dla pełnej asynchroniczności w Pythonie. Pamiętaj o obsłudze błędów połączenia i timeoutach.
* **Media:** Generowanie obrazów jest kosztowne czasowo/obliczeniowo. Uruchamiaj to jako zadanie w tle (`Scheduler` z PR 015).
* **Bezpieczeństwo:** Nigdy nie przesyłaj kluczy prywatnych SSH przez prompt LLM. `DevOpsAgent` powinien tylko wskazywać ścieżki do kluczy na dysku Nexusa.
* **Fallback:** Jeśli brak GPU dla Stable Diffusion, `MediaSkill` może używać prostego generatora placeholderów (np. `Pillow` do generowania grafik z tekstem) lub API zewnętrznego.
