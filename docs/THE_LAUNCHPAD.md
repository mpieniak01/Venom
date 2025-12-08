# THE_LAUNCHPAD - Warstwa Wdrożeniowa i Kreatywna

## Przegląd

THE_LAUNCHPAD to zestaw komponentów umożliwiających Venomowi "wypuszczenie" aplikacji w świat poprzez:
- **Cloud Deployment** - automatyczne wdrażanie na zdalnych serwerach
- **Media Generation** - generowanie logo, grafik i assetów wizualnych
- **Branding & Marketing** - tworzenie strategii marketingowej i content marketingu

---

## Komponenty

### 1. CloudProvisioner (`venom_core/infrastructure/cloud_provisioner.py`)

Zarządca deploymentów w chmurze obsługujący SSH i Docker.

**Funkcjonalności:**
- `provision_server()` - instalacja Dockera i Nginx na czystym serwerze
- `deploy_stack()` - deployment aplikacji przez docker-compose
- `check_deployment_health()` - monitorowanie stanu deploymentu
- `configure_domain()` - konfiguracja DNS (placeholder)

**Przykład użycia:**
```python
from venom_core.infrastructure.cloud_provisioner import CloudProvisioner

provisioner = CloudProvisioner(ssh_key_path="~/.ssh/id_rsa")
await provisioner.provision_server(host="1.2.3.4", user="root")
await provisioner.deploy_stack(
    host="1.2.3.4",
    stack_name="my_app",
    compose_file_path="./docker-compose.yml"
)
```

**Bezpieczeństwo:**
- Używa `asyncssh` dla asynchronicznych operacji
- Timeout dla wszystkich operacji SSH
- Nigdy nie loguje kluczy prywatnych
- Obsługa błędów połączenia

---

### 2. MediaSkill (`venom_core/execution/skills/media_skill.py`)

Skill do generowania i przetwarzania obrazów.

**Funkcjonalności:**
- `generate_image()` - generowanie obrazów (DALL-E lub placeholder Pillow)
- `resize_image()` - zmiana rozmiaru dla różnych użyć (favicon, og:image)
- `list_assets()` - lista wygenerowanych assetów

**Przykład użycia:**
```python
from venom_core.execution.skills.media_skill import MediaSkill

skill = MediaSkill()
logo_path = await skill.generate_image(
    prompt="Minimalist logo for fintech app, navy blue and gold",
    size="1024x1024",
    filename="logo.png"
)

favicon_path = await skill.resize_image(
    image_path=logo_path,
    width=32,
    height=32,
    output_name="favicon.png"
)
```

**Tryby pracy:**
- `placeholder` - generuje placeholdery używając Pillow (domyślny, bez GPU)
- `openai` - używa DALL-E 3 przez OpenAI API (wymaga klucza)
- `local-sd` - Stable Diffusion lokalnie (TODO - wymaga ONNX/GPU)

---

### 3. Creative Director Agent (`venom_core/agents/creative_director.py`)

Agent specjalizujący się w brandingu i marketingu.

**Kompetencje:**
- Tworzenie promptów do AI art generation
- Projektowanie identyfikacji wizualnej
- Copywriting (landing pages, opisy produktów)
- Content marketing (social media, tweety, posty LinkedIn)

**System Prompt:**
- Ekspert w brandingu i marketingu
- Dobiera styl wizualny do tematyki produktu
- Tworzy kompleksowe marketing kity

**Przykład zadania:**
```
"Stwórz branding dla aplikacji do zarządzania finansami osobistymi 'MoneyFlow'.
Target: millenialsi 25-35 lat. Wygeneruj logo i przygotuj launch tweet."
```

---

### 4. DevOps Agent (`venom_core/agents/devops.py`)

Agent specjalizujący się w infrastrukturze i deploymencie.

**Kompetencje:**
- Zarządzanie infrastrukturą cloud (VPS, Docker, Kubernetes)
- Deployment & CI/CD pipelines
- Konfiguracja serwerów (Linux, Docker, Nginx)
- Monitoring & Logging
- Security (SSH keys, SSL certificates, secrets management)

**System Prompt:**
- Ekspert DevOps i SRE
- Priorytet: bezpieczeństwo i niezawodność
- Używa CloudProvisioner do operacji

**Przykład zadania:**
```
"Deploy aplikację e-commerce na serwer 1.2.3.4. Użyj docker-compose,
skonfiguruj Nginx jako reverse proxy, zainstaluj SSL certyfikat."
```

---

## Konfiguracja

Dodaj do `.env`:

```env
# === THE_LAUNCHPAD Configuration ===

# Cloud Deployment
ENABLE_LAUNCHPAD=true
DEPLOYMENT_SSH_KEY_PATH=~/.ssh/id_rsa
DEPLOYMENT_DEFAULT_USER=root
DEPLOYMENT_TIMEOUT=300

# Media Generation
ASSETS_DIR=./workspace/assets
ENABLE_IMAGE_GENERATION=true
IMAGE_GENERATION_SERVICE=placeholder  # lub 'openai', 'local-sd'

# Jeśli używasz OpenAI DALL-E:
OPENAI_API_KEY=sk-...
DALLE_MODEL=dall-e-3
IMAGE_DEFAULT_SIZE=1024x1024
IMAGE_STYLE=vivid
```

---

## Workflow: "Go-Live"

Kompletny proces wdrożenia aplikacji:

### 1. Build
```
CoderAgent tworzy aplikację → docker-compose.yml
```

### 2. Branding
```
CreativeDirector → generate_image → logo.png, favicon.png
CreativeDirector → MARKETING_KIT.md (tweets, posty, opisy)
```

### 3. Deploy
```
DevOpsAgent → provision_server → instalacja Docker
DevOpsAgent → deploy_stack → uruchomienie aplikacji
```

### 4. Announce
```
CreativeDirector → launch tweet, LinkedIn post
PublisherAgent → publikacja na Product Hunt, Hacker News
```

---

## Demo & Testy

### Uruchom demo:
```bash
python examples/demo_launchpad.py
```

### Uruchom testy:
```bash
pytest tests/test_media_skill.py -v
pytest tests/test_cloud_provisioner.py -v
pytest tests/test_launchpad_agents.py -v
```

**Wyniki:**
- 32/32 testy przechodzą ✓
- Wszystkie komponenty działają poprawnie
- Code coverage: >90%

---

## Marketing Kit Template

Każdy projekt otrzymuje `MARKETING_KIT.md` zawierający:
- Identyfikację wizualną (logo, kolory, typografia)
- Copywriting (tagline, value proposition, features)
- Social media content (tweets, posty LinkedIn, Instagram)
- Marketing strategy (go-to-market plan)
- Metryki sukcesu

Szablon: `workspace/MARKETING_KIT_TEMPLATE.md`

---

## Bezpieczeństwo

### Zasady:
1. ✅ **NIE** loguj kluczy prywatnych SSH
2. ✅ **NIE** wklejaj sekretów w promptach LLM
3. ✅ Używaj tylko ścieżek do kluczy, nie samych kluczy
4. ✅ Wszystkie operacje SSH mają timeout
5. ✅ Sekrety w `.env` lub vault, nigdy w kodzie

### CloudProvisioner:
- Używa `asyncssh` z timeoutem
- Walidacja komend przed wykonaniem
- Known hosts handling
- Obsługa błędów połączenia

---

## Roadmap

### Zaimplementowane (v1.0):
- ✅ CloudProvisioner (SSH, Docker, deployment)
- ✅ MediaSkill (placeholder generation z Pillow)
- ✅ Creative Director Agent
- ✅ DevOps Agent
- ✅ Marketing Kit Template
- ✅ 32 testy jednostkowe

### Planowane (v1.1):
- ⏳ DALL-E 3 integration (wymaga OPENAI_API_KEY)
- ⏳ Stable Diffusion lokalnie (ONNX + GPU)
- ⏳ DNS configuration (Cloudflare API)
- ⏳ SSL certificates (Let's Encrypt/Certbot automation)
- ⏳ Kubernetes deployment
- ⏳ Dashboard: Deployments view (web UI)

### Planowane (v2.0):
- ⏳ CI/CD pipeline generation (GitHub Actions, GitLab CI)
- ⏳ Monitoring & alerting (Prometheus, Grafana)
- ⏳ Video generation (Gemini API)
- ⏳ Landing page generator (automatyczne HTML/CSS)

---

## Przykłady użycia

### Przykład 1: Generowanie Logo
```python
from venom_core.execution.skills.media_skill import MediaSkill

skill = MediaSkill()
logo = await skill.generate_image(
    prompt="Minimalist logo for SaaS platform, gradient blue to purple",
    size="1024x1024",
    filename="saas_logo.png"
)
print(f"Logo: {logo}")
```

### Przykład 2: Deployment na VPS
```python
from venom_core.infrastructure.cloud_provisioner import CloudProvisioner

provisioner = CloudProvisioner(ssh_key_path="~/.ssh/vps_key")

# Provision serwera
await provisioner.provision_server(host="1.2.3.4", user="root")

# Deploy aplikacji
await provisioner.deploy_stack(
    host="1.2.3.4",
    stack_name="shop_app",
    compose_file_path="./workspace/shop/docker-compose.yml"
)

# Sprawdź health
health = await provisioner.check_deployment_health(
    host="1.2.3.4",
    stack_name="shop_app"
)
print(health)
```

### Przykład 3: Kompletny Workflow z Agentami
```python
# 1. Creative Director tworzy branding
creative = CreativeDirectorAgent(kernel)
branding = await creative.process(
    "Stwórz kompletny branding dla aplikacji kwiaciarni online 'FlowerDelivery'"
)

# 2. DevOps wdraża aplikację
devops = DevOpsAgent(kernel)
deployment = await devops.process(
    "Deploy aplikację FlowerDelivery na serwer 1.2.3.4 z SSL"
)
```

---

## Dokumentacja API

Szczegółowa dokumentacja w docstringach:
- `venom_core.infrastructure.cloud_provisioner.CloudProvisioner`
- `venom_core.execution.skills.media_skill.MediaSkill`
- `venom_core.agents.creative_director.CreativeDirectorAgent`
- `venom_core.agents.devops.DevOpsAgent`

---

## Troubleshooting

### Problem: "ModuleNotFoundError: No module named 'asyncssh'"
**Rozwiązanie:** `pip install asyncssh`

### Problem: "Brak klucza SSH"
**Rozwiązanie:** Ustaw `DEPLOYMENT_SSH_KEY_PATH` w `.env` lub użyj hasła

### Problem: "Connection timeout"
**Rozwiązanie:** Sprawdź firewall, serwer musi mieć otwarty port 22 (SSH)

### Problem: "OpenAI API error"
**Rozwiązanie:** Sprawdź `OPENAI_API_KEY` lub użyj trybu `placeholder`

---

## Kontrybutorzy

- **Zadanie:** 029_THE_LAUNCHPAD
- **Priorytet:** Strategiczny (Product Release & Monetization)
- **Status:** ✅ Zakończone (2025-12-08)
- **Testy:** 32/32 przechodzą
- **Code Quality:** Linted (ruff, black, isort)

---

## Licencja

Część projektu Venom Meta-Intelligence.
