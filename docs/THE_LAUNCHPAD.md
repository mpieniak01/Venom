# THE_LAUNCHPAD - Deployment and Creative Layer

## Overview

THE_LAUNCHPAD is a set of components enabling Venom to "release" applications to the world through:
- **Cloud Deployment** - automatic deployment on remote servers
- **Media Generation** - generating logos, graphics and visual assets
- **Branding & Marketing** - creating marketing strategy and content marketing

---

## Components

### 1. CloudProvisioner (`venom_core/infrastructure/cloud_provisioner.py`)

Cloud deployment manager supporting SSH and Docker.

**Features:**
- `provision_server()` - installing Docker and Nginx on clean server
- `deploy_stack()` - application deployment via docker-compose
- `check_deployment_health()` - deployment state monitoring
- `configure_domain()` - DNS configuration (placeholder)

**Usage Example:**
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

**Security:**
- Uses `asyncssh` for asynchronous operations
- Timeout for all SSH operations
- Never logs private keys
- Connection error handling

---

### 2. MediaSkill (`venom_core/execution/skills/media_skill.py`)

Skill for generating and processing images.

**Features:**
- `generate_image()` - image generation (DALL-E or placeholder Pillow)
- `resize_image()` - resizing for different uses (favicon, og:image)
- `list_assets()` - list of generated assets

**Usage Example:**
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

**Operation Modes:**
- `placeholder` - generates placeholders using Pillow (default, no GPU)
- `openai` - uses DALL-E 3 via OpenAI API (requires key)
- `local-sd` - Stable Diffusion locally (TODO - requires ONNX/GPU)

---

### 3. Creative Director Agent (`venom_core/agents/creative_director.py`)

Agent specializing in branding and marketing.

**Competencies:**
- Creating prompts for AI art generation
- Visual identity design
- Copywriting (landing pages, product descriptions)
- Content marketing (social media, tweets, LinkedIn posts)

**System Prompt:**
- Branding and marketing expert
- Selects visual style matching product theme
- Creates comprehensive marketing kits

**Example Task:**
```
"Create branding for personal finance management app 'MoneyFlow'.
Target: millennials 25-35 years. Generate logo and prepare launch tweet."
```

---

### 4. DevOps Agent (`venom_core/agents/devops.py`)

Agent specializing in infrastructure and deployment.

**Competencies:**
- Cloud infrastructure management (VPS, Docker, Kubernetes)
- Deployment & CI/CD pipelines
- Server configuration (Linux, Docker, Nginx)
- Monitoring & Logging
- Security (SSH keys, SSL certificates, secrets management)

**System Prompt:**
- DevOps and SRE expert
- Priority: security and reliability
- Uses CloudProvisioner for operations

**Example Task:**
```
"Deploy e-commerce app on server 1.2.3.4. Use docker-compose,
configure Nginx as reverse proxy, install SSL certificate."
```

---

## Configuration

Add to `.env`:

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
IMAGE_GENERATION_SERVICE=placeholder  # or 'openai', 'local-sd'

# If using OpenAI DALL-E:
OPENAI_API_KEY=sk-...
DALLE_MODEL=dall-e-3
IMAGE_DEFAULT_SIZE=1024x1024
IMAGE_STYLE=vivid
```

---

## Workflow: "Go-Live"

Complete application deployment process:

### 1. Build
```
CoderAgent creates application → docker-compose.yml
```

### 2. Branding
```
CreativeDirector → generate_image → logo.png, favicon.png
CreativeDirector → MARKETING_KIT.md (tweets, posts, descriptions)
```

### 3. Deploy
```
DevOpsAgent → provision_server → Docker installation
DevOpsAgent → deploy_stack → application launch
```

### 4. Announce
```
CreativeDirector → launch tweet, LinkedIn post
PublisherAgent → publication on Product Hunt, Hacker News
```

---

## Demo & Tests

### Run demo:
```bash
python examples/demo_launchpad.py
```

### Run tests:
```bash
pytest tests/test_media_skill.py -v
pytest tests/test_cloud_provisioner.py -v
pytest tests/test_launchpad_agents.py -v
```

**Results:**
- 32/32 tests pass ✓
- All components working correctly
- Code coverage: >90%

---

## Marketing Kit Template

Each project receives `MARKETING_KIT.md` containing:
- Visual identity (logo, colors, typography)
- Copywriting (tagline, value proposition, features)
- Social media content (tweets, LinkedIn posts, Instagram)
- Marketing strategy (go-to-market plan)
- Success metrics

Template: `workspace/MARKETING_KIT_TEMPLATE.md`

---

## Security

### Principles:
1. ✅ **DO NOT** log SSH private keys
2. ✅ **DO NOT** paste secrets in LLM prompts
3. ✅ Use only paths to keys, not keys themselves
4. ✅ All SSH operations have timeout
5. ✅ Secrets in `.env` or vault, never in code

### CloudProvisioner:
- Uses `asyncssh` with timeout
- Command validation before execution
- Known hosts handling
- Connection error handling

---

## Roadmap

### Implemented (v1.0):
- ✅ CloudProvisioner (SSH, Docker, deployment)
- ✅ MediaSkill (placeholder generation with Pillow)
- ✅ Creative Director Agent
- ✅ DevOps Agent
- ✅ Marketing Kit Template
- ✅ 32 unit tests

### Planned (v1.1):
- ⏳ DALL-E 3 integration (requires OPENAI_API_KEY)
- ⏳ Stable Diffusion locally (ONNX + GPU)
- ❌ DNS configuration (Cloudflare API) - **REMOVED**: Replaced by mDNS (venom.local)
- ⏳ SSL certificates (Let's Encrypt/Certbot automation)
- ⏳ Kubernetes deployment
- ⏳ Dashboard: Deployments view (web UI)

### Planned (v2.0):
- ⏳ CI/CD pipeline generation (GitHub Actions, GitLab CI)
- ⏳ Monitoring & alerting (Prometheus, Grafana)
- ⏳ Video generation (Gemini API)
- ⏳ Landing page generator (automatic HTML/CSS)

---

## Usage Examples

### Example 1: Logo Generation
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

### Example 2: VPS Deployment
```python
from venom_core.infrastructure.cloud_provisioner import CloudProvisioner

provisioner = CloudProvisioner(ssh_key_path="~/.ssh/vps_key")

# Provision server
await provisioner.provision_server(host="1.2.3.4", user="root")

# Deploy application
await provisioner.deploy_stack(
    host="1.2.3.4",
    stack_name="shop_app",
    compose_file_path="./workspace/shop/docker-compose.yml"
)

# Check health
health = await provisioner.check_deployment_health(
    host="1.2.3.4",
    stack_name="shop_app"
)
print(health)
```

### Example 3: Complete Workflow with Agents
```python
# 1. Creative Director creates branding
creative = CreativeDirectorAgent(kernel)
branding = await creative.process(
    "Create complete branding for online florist app 'FlowerDelivery'"
)

# 2. DevOps deploys application
devops = DevOpsAgent(kernel)
deployment = await devops.process(
    "Deploy FlowerDelivery app on server 1.2.3.4 with SSL"
)
```

---

## API Documentation

Detailed documentation in docstrings:
- `venom_core.infrastructure.cloud_provisioner.CloudProvisioner`
- `venom_core.execution.skills.media_skill.MediaSkill`
- `venom_core.agents.creative_director.CreativeDirectorAgent`
- `venom_core.agents.devops.DevOpsAgent`

---

## Troubleshooting

### Problem: "ModuleNotFoundError: No module named 'asyncssh'"
**Solution:** `pip install asyncssh`

### Problem: "No SSH key"
**Solution:** Set `DEPLOYMENT_SSH_KEY_PATH` in `.env` or use password

### Problem: "Connection timeout"
**Solution:** Check firewall, server must have open port 22 (SSH)

### Problem: "OpenAI API error"
**Solution:** Check `OPENAI_API_KEY` or use `placeholder` mode

---

## Contributors

- **Task:** 029_THE_LAUNCHPAD
- **Priority:** Strategic (Product Release & Monetization)
- **Status:** ✅ Completed (2025-12-08)
- **Tests:** 32/32 passing
- **Code Quality:** Linted (ruff, black, isort)

---

## License

Part of the Venom Meta-Intelligence project.
