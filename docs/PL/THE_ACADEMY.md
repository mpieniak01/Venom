# THE ACADEMY - Knowledge Distillation & Autonomous Fine-Tuning

## Przegląd

> Uwaga (źródło prawdy):
> README zawiera tylko skrót modułu Academy. Ten dokument jest dedykowaną
> referencją modułu: architektura, konfiguracja, API i operacje.

THE ACADEMY to system uczenia maszynowego, który pozwala Venomowi na autonomiczne doskonalenie się poprzez:
- **Destylację Wiedzy** - ekstrakcję cennych wzorców z historii działań
- **Fine-tuning LoRA** - szybkie douczanie modelu bez nadpisywania bazowej wiedzy
- **Hot Swap** - bezproblemowa wymiana "mózgu" na nowszą wersję
- **Genealogię Inteligencji** - śledzenie ewolucji modelu

## Architektura

```
┌─────────────────────────────────────────────────────────────┐
│                      THE ACADEMY                             │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐        ┌──────────────┐                   │
│  │  Lessons     │        │  Git History │                   │
│  │  Store       │        │  & Tasks     │                   │
│  └──────┬───────┘        └──────┬───────┘                   │
│         │                       │                            │
│         └───────────┬───────────┘                            │
│                     ▼                                        │
│            ┌────────────────┐                                │
│            │ DatasetCurator │                                │
│            └────────┬───────┘                                │
│                     │ dataset.jsonl                          │
│                     ▼                                        │
│            ┌────────────────┐                                │
│            │   Professor    │ ◄─── Decyzje, parametry       │
│            └────────┬───────┘                                │
│                     │                                        │
│                     ▼                                        │
│            ┌────────────────┐                                │
│            │  GPUHabitat    │ ◄─── Trening w Dockerze       │
│            └────────┬───────┘                                │
│                     │ adapter.pth                            │
│                     ▼                                        │
│            ┌────────────────┐                                │
│            │ ModelManager   │ ◄─── Hot Swap, Wersjonowanie  │
│            └────────────────┘                                │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Komponenty

### 1. DatasetCurator (`venom_core/learning/dataset_curator.py`)

**Cel:** Konwersja surowych danych w format treningowy (JSONL).

**Źródła danych:**
- **LessonsStore** - pary (Sytuacja → Rozwiązanie)
- **Git History** - analiza commitów (Diff → Commit Message)
- **Task History** - udane konwersacje z orchestratorem

**Formaty wyjściowe:**
- **Alpaca** - format instruction-input-output
- **ShareGPT** - format conversations (system-human-gpt)

**Przykład użycia:**

```python
from venom_core.learning.dataset_curator import DatasetCurator
from venom_core.memory.lessons_store import LessonsStore

# Inicjalizacja
lessons_store = LessonsStore()
curator = DatasetCurator(lessons_store=lessons_store)

# Zbieranie danych
curator.collect_from_lessons(limit=200)
curator.collect_from_git_history(max_commits=100)

# Filtrowanie
curator.filter_low_quality()

# Zapisz
dataset_path = curator.save_dataset(format="alpaca")
print(f"Dataset zapisany: {dataset_path}")

# Statystyki
stats = curator.get_statistics()
print(f"Liczba przykładów: {stats['total_examples']}")
```

### 2. GPUHabitat (`venom_core/infrastructure/gpu_habitat.py`)

**Cel:** Zarządzanie środowiskiem treningowym z obsługą GPU.

**Funkcjonalności:**
- Automatyczna detekcja GPU i nvidia-container-toolkit
- Uruchamianie kontenerów z Unsloth (bardzo szybki fine-tuning)
- Monitorowanie jobów treningowych
- Fallback na CPU jeśli brak GPU

**Przykład użycia:**

```python
from venom_core.infrastructure.gpu_habitat import GPUHabitat

# Inicjalizacja
habitat = GPUHabitat(enable_gpu=True)

# Uruchom trening
job_info = habitat.run_training_job(
    dataset_path="./data/training/dataset.jsonl",
    base_model="unsloth/Phi-3-mini-4k-instruct",
    output_dir="./data/models/training_0",
    lora_rank=16,
    learning_rate=2e-4,
    num_epochs=3,
)

print(f"Job ID: {job_info['job_name']}")
print(f"Kontener: {job_info['container_id']}")

# Monitoruj postęp
status = habitat.get_training_status(job_info['job_name'])
print(f"Status: {status['status']}")
print(f"Logi:\n{status['logs']}")
```

### 3. Professor (`venom_core/agents/professor.py`)

**Cel:** Agent Data Scientist - opiekun procesu nauki.

**Odpowiedzialności:**
- Decyzja o rozpoczęciu treningu (minimum 100 lekcji)
- Dobór parametrów (learning rate, epochs, LoRA rank)
- Ewaluacja modeli (Arena - porównanie wersji)
- Promocja lepszych modeli

**Komendy:**

```python
from venom_core.agents.professor import Professor

# Inicjalizacja
professor = Professor(kernel, dataset_curator, gpu_habitat, lessons_store)

# Sprawdź gotowość
decision = professor.should_start_training()
if decision["should_train"]:
    print("✅ Gotowy do treningu!")

# Generuj dataset
result = await professor.process("przygotuj materiały do nauki")

# Rozpocznij trening
result = await professor.process("rozpocznij trening")

# Sprawdź postęp
result = await professor.process("sprawdź postęp treningu")

# Oceń model
result = await professor.process("oceń model")
```

### 4. ModelManager (`venom_core/core/model_manager.py`)

**Cel:** Zarządzanie wersjami modeli i Hot Swap.

**Funkcjonalności:**
- Rejestracja wersji modeli
- Hot swap (wymiana bez restartu)
- Genealogia Inteligencji (historia wersji)
- Porównanie metryk między wersjami
- Integracja z Ollama (tworzenie Modelfile)

**Przykład użycia:**

```python
from venom_core.core.model_manager import ModelManager

# Inicjalizacja
manager = ModelManager()

# Zarejestruj wersje
manager.register_version(
    version_id="v1.0",
    base_model="phi3:latest",
    performance_metrics={"accuracy": 0.85}
)

manager.register_version(
    version_id="v1.1",
    base_model="phi3:latest",
    adapter_path="./data/models/adapter",
    performance_metrics={"accuracy": 0.92}
)

# Aktywuj nową wersję (hot swap)
manager.activate_version("v1.1")

# Porównaj wersje
comparison = manager.compare_versions("v1.0", "v1.1")
print(f"Improvement: {comparison['metrics_diff']['accuracy']['diff_pct']:.1f}%")

# Genealogia
genealogy = manager.get_genealogy()
for version in genealogy['versions']:
    print(f"{version['version_id']}: {version['performance_metrics']}")
```

## Workflow: Od Lekcji do Modelu

```
1. Zbieranie Doświadczeń
   └─> LessonsStore.add_lesson() po każdym sukcesie

2. Kuracja Datasetu (automatyczna lub on-demand)
   └─> DatasetCurator.collect_from_*()
   └─> Minimum 50-100 przykładów

3. Decyzja o Treningu
   └─> Professor.should_start_training()
   └─> Sprawdza: liczba lekcji, interwał od ostatniego treningu

4. Trening (w tle, Docker + GPU)
   └─> GPUHabitat.run_training_job()
   └─> Unsloth + LoRA (szybki, oszczędny VRAM)

5. Ewaluacja (Arena)
   └─> Professor ocenia: Stary Model vs Nowy Model
   └─> Test suite (10 pytań kodowania)

6. Promocja
   └─> ModelManager.activate_version()
   └─> Hot swap - Venom używa nowego modelu

7. Monitoring
   └─> Dashboard: wykresy Loss, statystyki, genealogia
```

## Konfiguracja

### Wymagania systemowe

**Minimalne (CPU only):**
- Docker zainstalowany
- 8 GB RAM
- Python 3.10+

**Zalecane (GPU):**
- NVIDIA GPU (min. 8 GB VRAM)
- nvidia-container-toolkit
- CUDA 12.0+
- 16 GB RAM

### Instalacja nvidia-container-toolkit (Ubuntu/Debian)

```bash
# Dodaj repozytorium NVIDIA
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# Instaluj
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Restart Docker
sudo systemctl restart docker

# Test
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

### Konfiguracja środowiska (`.env`)

```bash
# Ścieżki
WORKSPACE_ROOT=./workspace
MEMORY_ROOT=./data/memory

# Model bazowy dla fine-tuningu
DEFAULT_BASE_MODEL=unsloth/Phi-3-mini-4k-instruct

# Parametry treningowe
DEFAULT_LORA_RANK=16
DEFAULT_LEARNING_RATE=2e-4
DEFAULT_NUM_EPOCHS=3

# GPU
ENABLE_GPU=true
TRAINING_IMAGE=unsloth/unsloth:latest

# Kryteria treningu
MIN_LESSONS_FOR_TRAINING=100
MIN_TRAINING_INTERVAL_HOURS=24
```

## Przykład: Automatyzacja z Scheduler

```python
from venom_core.core.scheduler import BackgroundScheduler
from venom_core.agents.professor import Professor

async def auto_training_job():
    """Zadanie cykliczne - sprawdza czy pora na trening."""
    decision = professor.should_start_training()
    if decision["should_train"]:
        logger.info("Rozpoczynam automatyczny trening...")
        await professor.process("przygotuj materiały do nauki")
        await professor.process("rozpocznij trening")

# Dodaj do schedulera (co 24h)
scheduler = BackgroundScheduler()
scheduler.add_interval_job(
    func=auto_training_job,
    minutes=60 * 24,  # Raz dziennie
    job_id="auto_training",
    description="Automatyczny trening Venoma"
)
```

## Najlepsze Praktyki

1. **Jakość > Ilość**
   - Filtruj niepoprawne przykłady
   - Weryfikuj output przed dodaniem do LessonsStore
   - Używaj tagów do kategoryzacji

2. **Rozpocznij małym datasetom**
   - 50-100 przykładów na start
   - Monitoruj overfitting

3. **Regularność > Masywność**
   - Lepiej 100 nowych przykładów co tydzień niż 1000 raz na rok
   - Model "nie zapomina" dzięki LoRA

4. **Testuj przed promocją**
   - Arena - porównaj na testowym zestawie
   - Sprawdź regresję (czy nowy model nie jest gorszy w czymś)

5. **Backup modeli**
   - ModelManager trzyma historię
   - Możesz wrócić do poprzedniej wersji

## Troubleshooting

**Problem:** Trening się zawiesza
- **Rozwiązanie:** Zmniejsz `batch_size` lub `max_seq_length`

**Problem:** CUDA Out of Memory
- **Rozwiązanie:** Włącz `load_in_4bit=True` (już domyślne), zmniejsz `lora_rank`

**Problem:** Dataset za mały (< 50 przykładów)
- **Rozwiązanie:** Zbierz więcej lekcji, włącz Task History, analizuj więcej commitów

**Problem:** Model nie ulega poprawie
- **Rozwiązanie:**
  - Zwiększ `num_epochs` (np. 5-10)
  - Sprawdź jakość datasetu (czy są błędy?)
  - Użyj większego `learning_rate` (np. 3e-4)

## Roadmap

- [ ] Pełna implementacja Arena (automated evaluation)
- [ ] Dashboard - wizualizacja w czasie rzeczywistym
- [ ] Integracja z PEFT dla KernelBuilder
- [ ] Multi-modal learning (obrazy, audio)
- [ ] Distributed training (multiple GPUs)
- [ ] A/B testing dla modeli

## Referencje

- [Unsloth](https://github.com/unslothai/unsloth) - bardzo szybki fine-tuning
- [LoRA Paper](https://arxiv.org/abs/2106.09685) - Low-Rank Adaptation
- [PEFT](https://github.com/huggingface/peft) - Parameter-Efficient Fine-Tuning

---

**Status:** ✅ Core features zaimplementowane
**Wersja:** 1.0 (PR 022)
**Autor:** Venom Team
