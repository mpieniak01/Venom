from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Ignore unknown env vars in local .env without failing startup/tests.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Venom Meta-Intelligence"
    ENV: str = "development"

    WORKSPACE_ROOT: str = "./workspace"
    REPO_ROOT: str = "."
    MEMORY_ROOT: str = "./data/memory"
    STATE_FILE_PATH: str = "./data/memory/state_dump.json"
    # Endpoint używany do lokalnego wykrywania adresu IP hosta (bez wysyłania payloadu)
    # Używamy nazwy DNS zamiast hardcoded IP (łatwiejsza konfiguracja i mniej false-positive w skanerach).
    NETWORK_PROBE_HOST: str = "dns.google"
    NETWORK_PROBE_PORT: int = 80

    # Modele ONNX
    MODEL_PHI3_PATH: str = "models/phi3-mini-4k-instruct-onnx"

    # Konfiguracja LLM (Local-First Brain)
    LLM_SERVICE_TYPE: str = "local"  # Opcje: "local", "openai", "azure", "google"
    LLM_LOCAL_ENDPOINT: str = "http://localhost:11434/v1"  # Ollama/vLLM
    LLM_MODEL_NAME: str = "phi3:latest"
    LLM_LOCAL_API_KEY: str = "venom-local"  # Dummy key dla lokalnych serwerów
    OPENAI_API_KEY: str = ""  # Opcjonalne, wymagane tylko dla typu "openai"
    GOOGLE_API_KEY: str = ""  # Opcjonalne, wymagane dla Google Gemini
    LLM_WARMUP_ON_STARTUP: bool = True
    LLM_WARMUP_PROMPT: str = "Ping."
    LLM_WARMUP_TIMEOUT_SECONDS: float = 5.0
    LLM_WARMUP_MAX_TOKENS: int = 8
    LLM_KEEP_ALIVE: str = "5m"  # Domyślny keep_alive dla Ollama (np. 5m, 1h, -1)
    SIMPLE_MODE_SYSTEM_PROMPT: str = "Odpowiadaj po polsku."

    # Konfiguracja Hybrid AI Mode (Local First + Cloud Options)
    AI_MODE: str = "LOCAL"  # Opcje: "LOCAL", "HYBRID", "CLOUD"
    # LOCAL - tylko lokalne modele, chmura zablokowana
    # HYBRID - lokalne do prostych zadań, chmura do trudnych
    # CLOUD - wszystko w chmurze
    HYBRID_CLOUD_PROVIDER: str = (
        "google"  # Opcje: "google", "openai" (używane w trybie HYBRID/CLOUD)
    )
    HYBRID_LOCAL_MODEL: str = "llama3"  # Model lokalny dla prostych zadań
    HYBRID_CLOUD_MODEL: str = (
        "gemini-1.5-pro"  # Model chmurowy dla trudnych zadań (gemini-1.5-pro, gpt-4o)
    )
    SENSITIVE_DATA_LOCAL_ONLY: bool = (
        True  # ZAWSZE kieruj wrażliwe dane do lokalnego modelu
    )
    # Komendy sterujące lokalnymi serwerami LLM (opcjonalne, wykonywane w powłoce)
    VLLM_MODEL_PATH: str = "models/gemma-3-4b-it"
    VLLM_SERVED_MODEL_NAME: str = ""
    VLLM_HOST: str = "0.0.0.0"
    VLLM_PORT: int = 8001
    VLLM_GPU_MEMORY_UTILIZATION: float = 0.90
    VLLM_MAX_BATCHED_TOKENS: int = 2048
    VLLM_MAX_MODEL_LEN: int = 0  # 0 = auto-detect from model
    VLLM_MAX_NUM_SEQS: int = 0
    VLLM_ENDPOINT: str = "http://localhost:8001/v1"
    VLLM_CHAT_TEMPLATE: str = ""
    VLLM_ENFORCE_EAGER: bool = True  # Disable CUDA Graphs to save VRAM
    VLLM_START_COMMAND: str = ""
    VLLM_STOP_COMMAND: str = ""
    VLLM_RESTART_COMMAND: str = ""
    OLLAMA_START_COMMAND: str = ""
    OLLAMA_STOP_COMMAND: str = ""
    OLLAMA_RESTART_COMMAND: str = ""
    # Czy w trybach LOCAL/ECO zawsze wymuszać darmowe źródła (np. DuckDuckGo)
    LOW_COST_FORCE_DDG: bool = False

    # Konfiguracja Model Router (THE_STRATEGIST)
    ENABLE_MODEL_ROUTING: bool = True  # Włącz inteligentny routing modeli
    FORCE_LOCAL_MODEL: bool = False  # Wymusza użycie tylko lokalnego modelu
    ENABLE_MULTI_SERVICE: bool = (
        False  # Włącz inicjalizację wielu serwisów jednocześnie
    )
    INTENT_CLASSIFIER_TIMEOUT_SECONDS: float = (
        5.0  # Timeout LLM przy klasyfikacji intencji
    )
    ENABLE_META_LEARNING: bool = True  # Globalny przełącznik zapisu lekcji
    LESSONS_TTL_DAYS: int = 0  # Retencja lekcji (0 = wyłączona)
    LAST_MODEL_OLLAMA: str = ""  # Ostatnio wybrany model Ollama
    LAST_MODEL_VLLM: str = ""  # Ostatnio wybrany model vLLM
    PREVIOUS_MODEL_OLLAMA: str = ""  # Poprzedni model Ollama (fallback)
    PREVIOUS_MODEL_VLLM: str = ""  # Poprzedni model vLLM (fallback)
    ACTIVE_LLM_SERVER: str = ""  # Ostatnio aktywowany serwer LLM
    LLM_CONFIG_HASH: str = (
        ""  # Hash aktywnej konfiguracji LLM (endpoint+model+provider)
    )
    MODEL_GENERATION_OVERRIDES: str = (
        ""  # Override parametrów generacji per runtime/model
    )
    SUMMARY_STRATEGY: str = "llm_with_fallback"  # lub "heuristic_only"

    # Konfiguracja Prompt Manager
    PROMPTS_DIR: str = "./data/prompts"  # Katalog z plikami YAML promptów

    # Konfiguracja Token Economist
    ENABLE_CONTEXT_COMPRESSION: bool = True  # Włącz kompresję kontekstu
    MAX_CONTEXT_TOKENS: int = 4000  # Maksymalna liczba tokenów w kontekście

    # Konfiguracja Docker Sandbox
    DOCKER_IMAGE_NAME: str = "python:3.11-slim"
    ENABLE_SANDBOX: bool = True

    # Konfiguracja Background Tasks (THE_OVERMIND)
    VENOM_PAUSE_BACKGROUND_TASKS: bool = False  # Globalny wyłącznik dla zadań w tle
    ENABLE_AUTO_DOCUMENTATION: bool = True  # Automatyczna aktualizacja dokumentacji
    ENABLE_AUTO_GARDENING: bool = True  # Automatyczna refaktoryzacja w trybie Idle
    ENABLE_MEMORY_CONSOLIDATION: bool = False  # Konsolidacja pamięci (placeholder)
    ENABLE_HEALTH_CHECKS: bool = True  # Sprawdzanie zdrowia systemu
    WATCHER_DEBOUNCE_SECONDS: int = (
        5  # Czas debounce dla watchdog (unikanie wielokrotnych triggerów)
    )
    IDLE_THRESHOLD_MINUTES: int = (
        15  # Czas bezczynności przed uruchomieniem auto-gardening
    )
    GARDENER_COMPLEXITY_THRESHOLD: int = 10  # Próg złożoności dla auto-refaktoryzacji
    MEMORY_CONSOLIDATION_INTERVAL_MINUTES: int = 60  # Interwał konsolidacji pamięci
    HEALTH_CHECK_INTERVAL_MINUTES: int = 5  # Interwał sprawdzania zdrowia systemu

    # Konfiguracja External Integrations (THE_TEAMMATE)
    # UWAGA: Sekrety używają SecretStr aby zapobiec przypadkowemu logowaniu
    ENABLE_HF_INTEGRATION: bool = True  # Włącz integrację z Hugging Face
    HF_TOKEN: SecretStr = SecretStr("")  # Token Hugging Face API (opcjonalny)
    GITHUB_TOKEN: SecretStr = SecretStr("")  # Personal Access Token do GitHub API
    GITHUB_REPO_NAME: str = ""  # Nazwa repozytorium np. "mpieniak01/Venom"
    DISCORD_WEBHOOK_URL: SecretStr = SecretStr(
        ""
    )  # Webhook URL dla powiadomień Discord
    SLACK_WEBHOOK_URL: SecretStr = SecretStr("")  # Webhook URL dla powiadomień Slack
    ENABLE_ISSUE_POLLING: bool = False  # Włącz automatyczne sprawdzanie Issues
    ISSUE_POLLING_INTERVAL_MINUTES: int = 5  # Interwał sprawdzania nowych Issues

    # Tavily AI Search (opcjonalne, dla lepszej jakości wyszukiwania)
    TAVILY_API_KEY: SecretStr = SecretStr("")  # API Key dla Tavily AI Search

    # Konfiguracja Google Calendar Integration
    ENABLE_GOOGLE_CALENDAR: bool = False  # Włącz integrację z Google Calendar
    GOOGLE_CALENDAR_CREDENTIALS_PATH: str = (
        "./config/google_calendar_credentials.json"  # Ścieżka do OAuth2 credentials
    )
    GOOGLE_CALENDAR_TOKEN_PATH: str = "./config/google_calendar_token.json"  # Ścieżka do OAuth2 token (auto-generated)
    VENOM_CALENDAR_ID: str = (
        "venom_work_calendar"  # ID kalendarza Venoma (write-only, NOT 'primary')
    )
    VENOM_CALENDAR_NAME: str = "Venom Work"  # Nazwa kalendarza Venoma

    # Konfiguracja Audio Interface (THE_AVATAR)
    ENABLE_AUDIO_INTERFACE: bool = False  # Włącz interfejs głosowy (STT/TTS)
    WHISPER_MODEL_SIZE: str = (
        "base"  # Rozmiar modelu Whisper ('tiny', 'base', 'small', 'medium', 'large')
    )
    TTS_MODEL_PATH: str = ""  # Ścieżka do modelu Piper TTS (ONNX), puste = mock mode
    AUDIO_DEVICE: str = "cpu"  # Urządzenie dla modeli audio ('cpu', 'cuda')
    VAD_THRESHOLD: float = 0.5  # Próg Voice Activity Detection (0.0-1.0)
    SILENCE_DURATION: float = 1.5  # Czas ciszy (sekundy) oznaczający koniec wypowiedzi

    # Konfiguracja IoT Bridge (Rider-Pi)
    ENABLE_IOT_BRIDGE: bool = False  # Włącz komunikację z Raspberry Pi
    RIDER_PI_HOST: str = "localhost"  # Host Rider-Pi (ustaw przez ENV dla sieci LAN)
    RIDER_PI_PORT: int = 22  # Port SSH (22) lub HTTP (8888 dla pigpio)
    RIDER_PI_USERNAME: str = "pi"  # Nazwa użytkownika SSH
    RIDER_PI_PASSWORD: SecretStr = SecretStr(
        ""
    )  # Hasło SSH (opcjonalne jeśli używamy klucza)
    RIDER_PI_KEY_FILE: str = ""  # Ścieżka do klucza SSH (opcjonalne)
    RIDER_PI_PROTOCOL: str = "ssh"  # Protokół komunikacji ('ssh' lub 'http')
    IOT_REQUIRE_CONFIRMATION: bool = (
        True  # Wymagaj potwierdzenia dla komend sprzętowych
    )

    # Konfiguracja THE_ACADEMY (Knowledge Distillation & Fine-tuning)
    ENABLE_ACADEMY: bool = True  # Włącz system uczenia maszynowego
    ACADEMY_TRAINING_DIR: str = "./data/training"  # Katalog z datasetami
    ACADEMY_MODELS_DIR: str = "./data/models"  # Katalog z modelami
    ACADEMY_MIN_LESSONS: int = 100  # Minimum lekcji do rozpoczęcia treningu
    ACADEMY_TRAINING_INTERVAL_HOURS: int = 24  # Minimum godzin między treningami
    ACADEMY_DEFAULT_BASE_MODEL: str = (
        "unsloth/Phi-3-mini-4k-instruct"  # Model bazowy do fine-tuningu
    )
    ACADEMY_LORA_RANK: int = 16  # LoRA rank (4-64, wyższe = więcej parametrów)
    ACADEMY_LEARNING_RATE: float = 2e-4  # Learning rate dla treningu
    ACADEMY_NUM_EPOCHS: int = 3  # Liczba epok treningu
    ACADEMY_BATCH_SIZE: int = 4  # Batch size (zmniejsz jeśli OOM)
    ACADEMY_MAX_SEQ_LENGTH: int = 2048  # Maksymalna długość sekwencji
    ACADEMY_ENABLE_GPU: bool = True  # Czy używać GPU (jeśli dostępne)
    ACADEMY_TRAINING_IMAGE: str = "unsloth/unsloth:latest"  # Obraz Docker dla treningu

    # Konfiguracja THE_NEXUS (Distributed Mesh)
    ENABLE_NEXUS: bool = False  # Włącz tryb Nexus (master node)
    NEXUS_SHARED_TOKEN: SecretStr = SecretStr(
        ""
    )  # Shared token dla uwierzytelniania węzłów
    NEXUS_HEARTBEAT_TIMEOUT: int = 60  # Timeout heartbeat w sekundach (domyślnie 60s)
    NEXUS_PORT: int = 8765  # Port WebSocket dla węzłów (domyślnie 8765)

    # Konfiguracja THE_HIVE (Distributed Processing & Task Queue)
    ENABLE_HIVE: bool = False  # Włącz architekturę rozproszonego przetwarzania
    HIVE_URL: str = ""  # URL centralnego Ula (np. https://hive.example.com:8080)
    HIVE_REGISTRATION_TOKEN: SecretStr = SecretStr(
        ""
    )  # Token autoryzacji dla rejestracji w Ulu
    REDIS_HOST: str = "localhost"  # Host Redis (dla Docker: 'redis')
    REDIS_PORT: int = 6379  # Port Redis
    REDIS_DB: int = 0  # Numer bazy danych Redis
    REDIS_PASSWORD: SecretStr = SecretStr("")  # Hasło Redis (opcjonalne)
    HIVE_HIGH_PRIORITY_QUEUE: str = "venom:tasks:high"  # Kolejka high priority
    HIVE_BACKGROUND_QUEUE: str = "venom:tasks:background"  # Kolejka background
    HIVE_BROADCAST_CHANNEL: str = "venom:broadcast"  # Kanał broadcast
    HIVE_TASK_TIMEOUT: int = 300  # Timeout zadania w sekundach (5 minut)
    HIVE_MAX_RETRIES: int = 3  # Maksymalna liczba prób wykonania zadania
    HIVE_ZOMBIE_TASK_TIMEOUT: int = 600  # Timeout dla zombie tasks (10 minut)

    # Konfiguracja THE_SIMULACRUM (Simulation Layer)
    ENABLE_SIMULATION: bool = False  # Włącz warstwę symulacji użytkowników
    SIMULATION_CHAOS_ENABLED: bool = False  # Włącz Chaos Engineering w symulacjach
    SIMULATION_MAX_STEPS: int = 10  # Maksymalna liczba kroków na użytkownika
    SIMULATION_USER_MODEL: str = (
        "local"  # Model dla symulowanych użytkowników (local/flash)
    )
    SIMULATION_ANALYST_MODEL: str = "openai"  # Model dla UX Analyst (openai/local)
    SIMULATION_DEFAULT_USERS: int = 5  # Domyślna liczba użytkowników w symulacji
    SIMULATION_LOGS_DIR: str = (
        "./workspace/simulation_logs"  # Katalog z logami symulacji
    )

    # Konfiguracja THE_LAUNCHPAD (Cloud Deployment & Creative Media)
    ENABLE_LAUNCHPAD: bool = False  # Włącz możliwość cloud deployment
    DEPLOYMENT_SSH_KEY_PATH: str = ""  # Ścieżka do klucza SSH dla deploymentu
    DEPLOYMENT_DEFAULT_USER: str = "root"  # Domyślny użytkownik SSH
    DEPLOYMENT_TIMEOUT: int = 300  # Timeout dla operacji SSH (sekundy)
    ASSETS_DIR: str = "./workspace/assets"  # Katalog dla wygenerowanych assetów
    ENABLE_IMAGE_GENERATION: bool = True  # Włącz generowanie obrazów
    IMAGE_GENERATION_SERVICE: str = (
        "placeholder"  # Serwis: 'placeholder', 'openai', 'local-sd'
    )
    DALLE_MODEL: str = "dall-e-3"  # Model DALL-E (jeśli używamy OpenAI)
    IMAGE_DEFAULT_SIZE: str = "1024x1024"  # Domyślny rozmiar obrazu
    IMAGE_STYLE: str = "vivid"  # Styl obrazu dla DALL-E: 'vivid' lub 'natural'

    # Konfiguracja THE_SHADOW (Desktop Awareness & Proactive Assistance)
    ENABLE_PROACTIVE_MODE: bool = False  # Włącz tryb proaktywny (Shadow Agent)
    ENABLE_DESKTOP_SENSOR: bool = False  # Włącz monitorowanie pulpitu (okna, schowek)
    SHADOW_CONFIDENCE_THRESHOLD: float = 0.8  # Próg pewności dla sugestii (0.0-1.0)
    SHADOW_PRIVACY_FILTER: bool = True  # Włącz filtr prywatności dla schowka
    SHADOW_CLIPBOARD_MAX_LENGTH: int = 1000  # Maksymalna długość tekstu ze schowka
    SHADOW_CHECK_INTERVAL: int = 1  # Interwał sprawdzania sensora (sekundy)

    # Konfiguracja THE_GHOST (Visual GUI Automation)
    ENABLE_GHOST_AGENT: bool = False  # Włącz Ghost Agent (kontrola GUI)
    GHOST_MAX_STEPS: int = 20  # Maksymalna liczba kroków w jednym zadaniu
    GHOST_STEP_DELAY: float = 1.0  # Opóźnienie między krokami (sekundy)
    GHOST_VERIFICATION_ENABLED: bool = True  # Weryfikacja po każdym kroku
    GHOST_SAFETY_DELAY: float = 0.5  # Opóźnienie bezpieczeństwa dla input operations
    GHOST_VISION_CONFIDENCE: float = 0.7  # Próg pewności dla vision grounding

    # Konfiguracja THE_DREAMER (Synthetic Experience Replay & Active Learning)
    ENABLE_DREAMING: bool = (
        False  # [v2.0] System aktywnego śnienia (przesunięty do wersji 2.0)
    )
    DREAMING_IDLE_THRESHOLD_MINUTES: int = (
        30  # Czas bezczynności przed rozpoczęciem śnienia
    )
    DREAMING_NIGHT_HOURS: str = (
        "2-6"  # Godziny nocne dla intensywnego śnienia (np. "2-6")
    )
    DREAMING_MAX_SCENARIOS: int = 10  # Maksymalna liczba scenariuszy na sesję śnienia
    DREAMING_CPU_THRESHOLD: float = (
        0.7  # Próg użycia CPU dla przerwania śnienia (0.0-1.0)
    )
    DREAMING_MEMORY_THRESHOLD: float = 0.8  # Próg użycia pamięci (0.0-1.0)
    DREAMING_SCENARIO_COMPLEXITY: str = (
        "medium"  # Złożoność scenariuszy: 'simple', 'medium', 'complex'
    )
    DREAMING_VALIDATION_STRICT: bool = (
        True  # Ultra-surowa walidacja snów przez Guardian
    )
    DREAMING_OUTPUT_DIR: str = (
        "./data/synthetic_training"  # Katalog dla syntetycznych danych
    )
    DREAMING_DOCKER_NAMESPACE: str = "venom-dream-worker"  # Namespace Docker dla snów
    DREAMING_PROCESS_PRIORITY: int = 19  # Priorytet procesu (0-19, 19=najniższy)

    # Konfiguracja THE_CHRONOMANCER (State Management & Timeline Branching)
    ENABLE_CHRONOS: bool = True  # Włącz system zarządzania stanem
    CHRONOS_TIMELINES_DIR: str = "./data/timelines"  # Katalog dla snapshotów
    CHRONOS_AUTO_CHECKPOINT: bool = (
        True  # Automatyczne checkpointy przed ryzykownymi operacjami
    )
    CHRONOS_MAX_CHECKPOINTS_PER_TIMELINE: int = (
        50  # Maksymalna liczba checkpointów na timeline
    )
    CHRONOS_CHECKPOINT_RETENTION_DAYS: int = (
        30  # Czas przechowywania checkpointów (dni)
    )
    CHRONOS_COMPRESS_SNAPSHOTS: bool = (
        True  # Kompresja snapshotów (oszczędność miejsca)
    )

    # Konfiguracja Queue Governance (Dashboard v2.3)
    MAX_CONCURRENT_TASKS: int = 5  # Maksymalna liczba równoczesnych zadań
    ENABLE_QUEUE_LIMITS: bool = True  # Włącz limity kolejki zadań

    # Konfiguracja Tokenomics (Dashboard v2.3)
    TOKEN_COST_ESTIMATION_SPLIT: float = (
        0.5  # Stosunek input/output dla estymacji kosztów
    )
    DEFAULT_COST_MODEL: str = "gpt-3.5-turbo"  # Domyślny model dla estymacji kosztów

    # ===== STABLE DIFFUSION CONFIGURATION =====
    # Endpoint dla Stable Diffusion (Automatic1111 API)
    STABLE_DIFFUSION_ENDPOINT: str = "http://127.0.0.1:7860"
    # Timeouty dla Stable Diffusion API
    SD_PING_TIMEOUT: float = 5.0  # Timeout dla sprawdzenia dostępności API (sekundy)
    SD_GENERATION_TIMEOUT: float = 120.0  # Timeout dla generowania obrazu (sekundy)
    # Domyślne parametry generowania obrazów
    SD_DEFAULT_STEPS: int = 20  # Liczba kroków generowania
    SD_DEFAULT_CFG_SCALE: float = 7.0  # CFG Scale (classifier-free guidance)
    SD_DEFAULT_SAMPLER: str = "DPM++ 2M Karras"  # Sampler dla SD

    # ===== AI MODELS CONFIGURATION =====
    # Modele OpenAI
    OPENAI_GPT4O_MODEL: str = "gpt-4o"  # Model GPT-4o dla vision i zaawansowanych zadań
    OPENAI_GPT4O_MINI_MODEL: str = "gpt-4o-mini"  # Model GPT-4o Mini
    OPENAI_GPT4_TURBO_MODEL: str = "gpt-4-turbo"  # Model GPT-4 Turbo
    OPENAI_GPT35_TURBO_MODEL: str = "gpt-3.5-turbo"  # Model GPT-3.5 Turbo
    # Modele Google
    GOOGLE_GEMINI_FLASH_MODEL: str = "gemini-1.5-flash"  # Model Gemini Flash
    GOOGLE_GEMINI_PRO_MODEL: str = (
        "gemini-1.5-pro"  # Model Gemini Pro (używany jako HYBRID_CLOUD_MODEL)
    )
    GOOGLE_GEMINI_PRO_LEGACY_MODEL: str = "gemini-pro"  # Legacy Gemini Pro
    # Modele Claude
    CLAUDE_OPUS_MODEL: str = "claude-opus"  # Model Claude Opus
    CLAUDE_SONNET_MODEL: str = "claude-sonnet"  # Model Claude Sonnet
    # Modele lokalne
    LOCAL_LLAMA3_MODEL: str = "llama3"  # Model Llama3 (domyślny lokalny)
    LOCAL_PHI3_MODEL: str = "phi3:latest"  # Model Phi3
    # Wzorce nazw modeli lokalnych (do wykrywania)
    LOCAL_MODEL_PATTERNS: list[str] = [
        "local",
        "phi",
        "mistral",
        "llama",
        "gemma",
        "qwen",
    ]
    # Nazwy modeli vision (do wykrywania w Ollama)
    VISION_MODEL_NAMES: list[str] = ["llava", "vision", "moondream", "bakllava"]

    # ===== DOCKER IMAGES CONFIGURATION =====
    # Obraz CUDA dla GPU operations
    DOCKER_CUDA_IMAGE: str = "nvidia/cuda:12.0.0-base-ubuntu22.04"
    # Obraz Redis dla Hive
    DOCKER_REDIS_IMAGE: str = "redis:7-alpine"
    # Obraz Node.js dla przykładów DevOps
    DOCKER_NODE_IMAGE: str = "node:18-alpine"
    # Obraz treningowy (domyślnie już jest jako ACADEMY_TRAINING_IMAGE)

    # ===== API TIMEOUTS CONFIGURATION =====
    # Timeout dla OpenAI API (vision, chat completions)
    OPENAI_API_TIMEOUT: float = 30.0
    # Timeout dla lokalnego modelu vision
    LOCAL_VISION_TIMEOUT: float = 60.0
    # Timeout dla sprawdzania dostępności Ollama
    OLLAMA_CHECK_TIMEOUT: float = 2.0
    # Timeout dla HTTP requests (ogólny)
    HTTP_REQUEST_TIMEOUT: float = 30.0
    # Maksymalna długość podsumowania news/papers
    NEWS_SUMMARY_MAX_CHARS: int = 240
    # Timeouty tłumaczeń (sekundy)
    TRANSLATION_TIMEOUT_NEWS: float = 6.0
    TRANSLATION_TIMEOUT_PAPERS: float = 8.0

    # ===== TOKEN ECONOMIST CONFIGURATION =====
    # Rezerwa tokenów dla podsumowania przy kompresji
    RESERVE_TOKENS_FOR_SUMMARY: int = 500
    # Ścieżka do pliku z cennikiem tokenów (YAML)
    PRICING_FILE_PATH: str = "./config/pricing.yaml"

    # ===== MODEL ROUTER CONFIGURATION =====
    # Próg bezpieczeństwa kosztów (USD)
    COST_THRESHOLD_USD: float = 0.01
    # Próg złożoności dla routingu (Low-Cost: < 5 -> LOCAL)
    COMPLEXITY_THRESHOLD_LOCAL: int = 5

    # ===== VISION & PERCEPTION CONFIGURATION =====
    # Minimalna długość base64 do rozróżnienia od ścieżki pliku
    MIN_BASE64_LENGTH: int = 500
    # Domyślny próg pewności dla vision grounding
    DEFAULT_VISION_CONFIDENCE: float = 0.7
    # Max tokens dla vision API responses
    VISION_MAX_TOKENS: int = 500
    # Max tokens dla vision grounding responses
    VISION_GROUNDING_MAX_TOKENS: int = 100

    # ===== OPENAI API ENDPOINTS =====
    # Endpoint OpenAI Chat Completions API
    OPENAI_CHAT_COMPLETIONS_ENDPOINT: str = "https://api.openai.com/v1/chat/completions"

    # ===== SYSTEM & MONITORING ENDPOINTS =====
    # Endpoint dla API systemowego (ServiceMonitor)
    SYSTEM_SERVICES_ENDPOINT: str = "http://localhost:8000/api/v1/system/services"

    # ===== BRAIN / GRAPH LIMITS (UI) =====
    NEXT_PUBLIC_KNOWLEDGE_GRAPH_LIMIT: int = 500
    NEXT_PUBLIC_MEMORY_GRAPH_LIMIT: int = 100

    # ===== FOREMAN (Load Balancer) CONFIGURATION =====
    # Wagi priorytetów dla obliczania obciążenia węzła (TD-010)
    # Suma wag powinna wynosić 1.0 (100%)
    FOREMAN_CPU_WEIGHT: float = 0.4  # Waga użycia CPU (0.4 = 40%)
    FOREMAN_MEMORY_WEIGHT: float = 0.3  # Waga użycia pamięci (0.3 = 30%)
    FOREMAN_TASKS_WEIGHT: float = 0.3  # Waga liczby aktywnych zadań (0.3 = 30%)
    FOREMAN_MAX_TASKS_NORMALIZATION: int = (
        10  # Maksymalna liczba zadań dla normalizacji
    )


SETTINGS = Settings()
