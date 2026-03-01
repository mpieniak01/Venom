"use client";

const EMBEDDING_ROUTER_SECTION_KEYS = [
  "ENABLE_INTENT_EMBEDDING_ROUTER",
  "INTENT_EMBED_MODEL_NAME",
  "INTENT_EMBED_MIN_SCORE",
  "INTENT_EMBED_MARGIN",
] as const;

export type ParametersSection = {
  title: string;
  description: string;
  keys: string[];
};

export function getParametersSections(input: {
  t: (key: string) => string;
  vllmAvailableInProfile: boolean;
}): ParametersSection[] {
  const { t, vllmAvailableInProfile } = input;
  return [
    {
      title: t("config.parameters.sections.aiMode.title"),
      description: t("config.parameters.sections.aiMode.description"),
      keys: [
        "AI_MODE",
        "LLM_SERVICE_TYPE",
        "LLM_LOCAL_ENDPOINT",
        "LLM_MODEL_NAME",
        "LLM_LOCAL_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "SUMMARY_STRATEGY",
        "HYBRID_CLOUD_PROVIDER",
        "HYBRID_LOCAL_MODEL",
        "HYBRID_CLOUD_MODEL",
        "SENSITIVE_DATA_LOCAL_ONLY",
        "ENABLE_MODEL_ROUTING",
        "FORCE_LOCAL_MODEL",
        "ENABLE_MULTI_SERVICE",
      ],
    },
    {
      title: t("config.parameters.sections.commands.title"),
      description: t("config.parameters.sections.commands.description"),
      keys: [
        "OLLAMA_START_COMMAND",
        "OLLAMA_STOP_COMMAND",
        "OLLAMA_RESTART_COMMAND",
        ...(vllmAvailableInProfile
          ? [
              "VLLM_START_COMMAND",
              "VLLM_STOP_COMMAND",
              "VLLM_RESTART_COMMAND",
              "VLLM_ENDPOINT",
            ]
          : []),
      ],
    },
    ...(vllmAvailableInProfile
      ? [
          {
            title: t("config.parameters.sections.vllm_advanced.title"),
            description: t("config.parameters.sections.vllm_advanced.description"),
            keys: [
              "VLLM_MODEL_PATH",
              "VLLM_SERVED_MODEL_NAME",
              "VLLM_GPU_MEMORY_UTILIZATION",
              "VLLM_MAX_BATCHED_TOKENS",
            ],
          },
        ]
      : []),
    {
      title: t("config.parameters.sections.routing.title"),
      description: t("config.parameters.sections.routing.description"),
      keys: ["ENABLE_CONTEXT_COMPRESSION", "MAX_CONTEXT_TOKENS"],
    },
    {
      title: t("config.parameters.sections.embeddingRouter.title"),
      description: t("config.parameters.sections.embeddingRouter.description"),
      keys: [...EMBEDDING_ROUTER_SECTION_KEYS],
    },
    {
      title: t("config.parameters.sections.prompts.title"),
      description: t("config.parameters.sections.prompts.description"),
      keys: ["PROMPTS_DIR"],
    },
    {
      title: t("config.parameters.sections.hive.title"),
      description: t("config.parameters.sections.hive.description"),
      keys: [
        "ENABLE_HIVE",
        "HIVE_URL",
        "HIVE_REGISTRATION_TOKEN",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_DB",
        "REDIS_PASSWORD",
        "HIVE_HIGH_PRIORITY_QUEUE",
        "HIVE_BACKGROUND_QUEUE",
        "HIVE_BROADCAST_CHANNEL",
        "HIVE_TASK_TIMEOUT",
        "HIVE_MAX_RETRIES",
      ],
    },
    {
      title: t("config.parameters.sections.nexus.title"),
      description: t("config.parameters.sections.nexus.description"),
      keys: [
        "ENABLE_NEXUS",
        "NEXUS_SHARED_TOKEN",
        "NEXUS_HEARTBEAT_TIMEOUT",
        "NEXUS_PORT",
      ],
    },
    {
      title: t("config.parameters.sections.tasks.title"),
      description: t("config.parameters.sections.tasks.description"),
      keys: [
        "VENOM_PAUSE_BACKGROUND_TASKS",
        "ENABLE_AUTO_DOCUMENTATION",
        "ENABLE_AUTO_GARDENING",
        "ENABLE_MEMORY_CONSOLIDATION",
        "ENABLE_HEALTH_CHECKS",
        "WATCHER_DEBOUNCE_SECONDS",
        "IDLE_THRESHOLD_MINUTES",
        "GARDENER_COMPLEXITY_THRESHOLD",
        "MEMORY_CONSOLIDATION_INTERVAL_MINUTES",
        "HEALTH_CHECK_INTERVAL_MINUTES",
      ],
    },
    {
      title: t("config.parameters.sections.sandbox.title"),
      description: t("config.parameters.sections.sandbox.description"),
      keys: ["ENABLE_SANDBOX", "DOCKER_IMAGE_NAME"],
    },
    {
      title: t("config.parameters.sections.shadow.title"),
      description: t("config.parameters.sections.shadow.description"),
      keys: [
        "ENABLE_PROACTIVE_MODE",
        "ENABLE_DESKTOP_SENSOR",
        "SHADOW_CONFIDENCE_THRESHOLD",
        "SHADOW_PRIVACY_FILTER",
        "SHADOW_CLIPBOARD_MAX_LENGTH",
        "SHADOW_CHECK_INTERVAL",
      ],
    },
    {
      title: t("config.parameters.sections.ghost.title"),
      description: t("config.parameters.sections.ghost.description"),
      keys: [
        "ENABLE_GHOST_AGENT",
        "GHOST_MAX_STEPS",
        "GHOST_STEP_DELAY",
        "GHOST_VERIFICATION_ENABLED",
        "GHOST_SAFETY_DELAY",
        "GHOST_VISION_CONFIDENCE",
      ],
    },
    {
      title: t("config.parameters.sections.avatar.title"),
      description: t("config.parameters.sections.avatar.description"),
      keys: [
        "ENABLE_AUDIO_INTERFACE",
        "WHISPER_MODEL_SIZE",
        "TTS_MODEL_PATH",
        "AUDIO_DEVICE",
        "VAD_THRESHOLD",
        "SILENCE_DURATION",
      ],
    },
    {
      title: t("config.parameters.sections.integrations.title"),
      description: t("config.parameters.sections.integrations.description"),
      keys: [
        "ENABLE_HF_INTEGRATION",
        "HF_TOKEN",
        "GITHUB_TOKEN",
        "GITHUB_REPO_NAME",
        "DISCORD_WEBHOOK_URL",
        "SLACK_WEBHOOK_URL",
        "ENABLE_ISSUE_POLLING",
        "ISSUE_POLLING_INTERVAL_MINUTES",
        "TAVILY_API_KEY",
      ],
    },
    {
      title: t("config.parameters.sections.calendar.title"),
      description: t("config.parameters.sections.calendar.description"),
      keys: [
        "ENABLE_GOOGLE_CALENDAR",
        "GOOGLE_CALENDAR_CREDENTIALS_PATH",
        "GOOGLE_CALENDAR_TOKEN_PATH",
        "VENOM_CALENDAR_ID",
        "VENOM_CALENDAR_NAME",
      ],
    },
    {
      title: t("config.parameters.sections.iot.title"),
      description: t("config.parameters.sections.iot.description"),
      keys: [
        "ENABLE_IOT_BRIDGE",
        "RIDER_PI_HOST",
        "RIDER_PI_PORT",
        "RIDER_PI_USERNAME",
        "RIDER_PI_PASSWORD",
        "RIDER_PI_KEY_FILE",
        "RIDER_PI_PROTOCOL",
        "IOT_REQUIRE_CONFIRMATION",
      ],
    },
    {
      title: t("config.parameters.sections.academy.title"),
      description: t("config.parameters.sections.academy.description"),
      keys: [
        "ENABLE_ACADEMY",
        "ACADEMY_TRAINING_DIR",
        "ACADEMY_MODELS_DIR",
        "ACADEMY_MIN_LESSONS",
        "ACADEMY_TRAINING_INTERVAL_HOURS",
        "ACADEMY_DEFAULT_BASE_MODEL",
        "ACADEMY_LORA_RANK",
        "ACADEMY_LEARNING_RATE",
        "ACADEMY_NUM_EPOCHS",
        "ACADEMY_BATCH_SIZE",
        "ACADEMY_MAX_SEQ_LENGTH",
        "ACADEMY_ENABLE_GPU",
        "ACADEMY_TRAINING_IMAGE",
      ],
    },
    {
      title: t("config.parameters.sections.simulations.title"),
      description: t("config.parameters.sections.simulations.description"),
      keys: [
        "ENABLE_SIMULATION",
        "SIMULATION_CHAOS_ENABLED",
        "SIMULATION_MAX_STEPS",
        "SIMULATION_USER_MODEL",
        "SIMULATION_ANALYST_MODEL",
        "SIMULATION_DEFAULT_USERS",
        "SIMULATION_LOGS_DIR",
      ],
    },
    {
      title: t("config.parameters.sections.launchpad.title"),
      description: t("config.parameters.sections.launchpad.description"),
      keys: [
        "ENABLE_LAUNCHPAD",
        "DEPLOYMENT_SSH_KEY_PATH",
        "DEPLOYMENT_DEFAULT_USER",
        "DEPLOYMENT_TIMEOUT",
        "ASSETS_DIR",
        "ENABLE_IMAGE_GENERATION",
        "IMAGE_GENERATION_SERVICE",
        "DALLE_MODEL",
        "IMAGE_DEFAULT_SIZE",
        "IMAGE_STYLE",
      ],
    },
    {
      title: t("config.parameters.sections.dreamer.title"),
      description: t("config.parameters.sections.dreamer.description"),
      keys: [
        "ENABLE_DREAMING",
        "DREAMING_IDLE_THRESHOLD_MINUTES",
        "DREAMING_NIGHT_HOURS",
        "DREAMING_MAX_SCENARIOS",
        "DREAMING_CPU_THRESHOLD",
        "DREAMING_MEMORY_THRESHOLD",
        "DREAMING_SCENARIO_COMPLEXITY",
        "DREAMING_VALIDATION_STRICT",
      ],
    },
  ];
}
