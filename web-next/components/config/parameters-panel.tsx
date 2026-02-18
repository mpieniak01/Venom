"use client";

import { useCallback, useEffect, useId, useState } from "react";
import { Save, Eye, EyeOff, AlertTriangle, Info, ChevronDown } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { SelectMenu } from "@/components/ui/select-menu";
import { useTranslation } from "@/lib/i18n";

interface Config {
  [key: string]: string;
}

interface ConfigSources {
  [key: string]: "env" | "default";
}

const EMBEDDING_ROUTER_SECTION = {
  title: "config.parameters.sections.embeddingRouter.title",
  description: "config.parameters.sections.embeddingRouter.description",
  keys: [
    "ENABLE_INTENT_EMBEDDING_ROUTER",
    "INTENT_EMBED_MODEL_NAME",
    "INTENT_EMBED_MIN_SCORE",
    "INTENT_EMBED_MARGIN",
  ],
} as const;

function ConfigSection({
  title,
  description,
  children,
}: Readonly<{
  title: string;
  description: string;
  children: React.ReactNode;
}>) {
  const [open, setOpen] = useState(false);
  const contentId = useId();

  return (
    <div className="glass-panel rounded-2xl box-subtle p-6">
      <Button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((prev) => !prev)}
        variant="ghost"
        size="sm"
        className="w-full items-start justify-between gap-4 text-left"
      >
        <div>
          <h3 className="heading-h3">{title}</h3>
          <p className="mt-1 text-hint">{description}</p>
        </div>
        <ChevronDown
          className={`mt-1 h-5 w-5 text-zinc-500 transition-transform duration-300 ${open ? "rotate-180" : ""
            }`}
        />
      </Button>
      <div
        id={contentId}
        className={`overflow-hidden transition-[max-height,opacity,transform] duration-300 ease-out ${open ? "max-h-[1200px] opacity-100 translate-y-0" : "max-h-0 opacity-0 -translate-y-1"
          }`}
      >
        <div className="pt-4 space-y-4">{children}</div>
      </div>
    </div>
  );
}

export function ParametersPanel() {
  const t = useTranslation();
  const [config, setConfig] = useState<Config>({});
  const [originalConfig, setOriginalConfig] = useState<Config>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(
    null
  );
  const [showSecrets, setShowSecrets] = useState<{ [key: string]: boolean }>({});
  const [restartRequired, setRestartRequired] = useState<string[]>([]);
  const [configSources, setConfigSources] = useState<ConfigSources>({});


  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/v1/config/runtime");

      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        const errorMessage =
          errorText || `${t("config.parameters.messages.fetchError")} (HTTP ${response.status})`;
        console.error("Błąd pobierania konfiguracji (HTTP):", response.status, errorText);
        setMessage({
          type: "error",
          text: errorMessage,
        });
        return;
      }

      const data = await response.json();
      if (data.status === "success") {
        setConfig(data.config);
        setOriginalConfig(data.config);
        setConfigSources(data.config_sources || {});
      } else {
        const errorMessage = data.message || t("config.parameters.messages.fetchError");
        setMessage({
          type: "error",
          text: errorMessage,
        });
      }
    } catch (error) {
      // Log error locally
      console.error("Błąd pobierania konfiguracji:", error);
      setMessage({
        type: "error",
        text: t("config.parameters.messages.fetchError"),
      });
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleChange = (key: string, value: string) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  const toggleSecret = (key: string) => {
    setShowSecrets((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const hasChanges = () => {
    return Object.keys(config).some((key) => config[key] !== originalConfig[key]);
  };

  const getChangedKeys = () => {
    return Object.keys(config).filter((key) => config[key] !== originalConfig[key]);
  };

  const handleSave = async () => {
    if (!hasChanges()) {
      setMessage({ type: "error", text: t("config.parameters.messages.noChanges") });
      return;
    }

    const changedKeys = getChangedKeys();
    const updates: { [key: string]: string } = {};
    changedKeys.forEach((key) => {
      updates[key] = config[key];
    });

    setSaving(true);
    setMessage(null);

    try {
      const response = await fetch("/api/v1/config/runtime", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates }),
      });

      const data = await response.json();

      if (data.success) {
        setMessage({ type: "success", text: data.message });
        setRestartRequired(data.restart_required || []);
        setOriginalConfig(config);
      } else {
        setMessage({ type: "error", text: data.message });
      }
    } catch (error) {
      setMessage({
        type: "error",
        text: error instanceof Error ? error.message : t("config.parameters.messages.saveError"),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setConfig(originalConfig);
    setMessage(null);
    setRestartRequired([]);
  };

  const isSecret = (key: string) => {
    return key.includes("KEY") || key.includes("TOKEN") || key.includes("PASSWORD");
  };
  const runtimeProfile = (config.VENOM_RUNTIME_PROFILE || "full").toLowerCase();
  const vllmAvailableInProfile = runtimeProfile === "full";

  const renderInput = (key: string, value: string) => {
    const secret = isSecret(key);
    const showValue = !secret || showSecrets[key];
    const valueSource = configSources[key] || "env";


    const isBooleanKey = (key: string, val: string) => {
      const k = key.toUpperCase();
      const v = val.toLowerCase();
      if (v === "true" || v === "false") return true;
      return (
        k.startsWith("ENABLE_") ||
        k.startsWith("IS_") ||
        k.startsWith("HAS_") ||
        k.startsWith("USE_") ||
        k.endsWith("_ENABLED")
      );
    };

    const isBool = isBooleanKey(key, value);

    return (
      <div key={key} className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-zinc-300">
            {key.replaceAll(/[_-]+/g, " ").replaceAll(/\b\w/g, (m) => m.toUpperCase())}
          </label>
          <div className="flex items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${valueSource === "default"
                ? "bg-amber-500/20 text-amber-300"
                : "bg-emerald-500/20 text-emerald-300"
                }`}
            >
              {valueSource === "default"
                ? t("config.parameters.valueSource.default")
                : t("config.parameters.valueSource.env")}
            </span>
            {secret && (
              <IconButton
                label={showValue ? t("config.parameters.sections.secrets.hide") : t("config.parameters.sections.secrets.show")}
                icon={showValue ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                variant="ghost"
                size="xs"
                className="text-zinc-500 hover:text-zinc-300"
                onClick={() => toggleSecret(key)}
              />
            )}
          </div>
        </div>
        {isBool ? (
          <SelectMenu
            value={value.toLowerCase() === "true" ? "true" : "false"}
            options={[
              { value: "true", label: "True" },
              { value: "false", label: "False" },
            ]}
            onChange={(newValue) => handleChange(key, newValue)}
            buttonClassName="w-full justify-between rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white hover:bg-white/5 hover:border-white/20 transition-colors"
            menuClassName="w-full"
          />
        ) : (
          <input
            type={showValue ? "text" : "password"}
            value={value}
            onChange={(e) => handleChange(key, e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-sm text-white outline-none focus:border-emerald-400 focus:ring-0"
          />
        )}
        {valueSource === "default" && (
          <p className="text-xs text-amber-200/80">{t("config.parameters.effectiveConfigHint")}</p>
        )}
      </div>
    );
  };

  const renderSection = (title: string, description: string, keys: string[]) => {
    const sectionKeys = keys.filter((key) => config.hasOwnProperty(key));
    if (sectionKeys.length === 0) return null;

    return (
      <ConfigSection title={title} description={description}>
        {sectionKeys.map((key) => renderInput(key, config[key] || ""))}
      </ConfigSection>
    );
  };

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="text-hint">{t("config.parameters.loading")}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Message */}
      {message && (
        <div
          className={`rounded-xl border p-4 ${message.type === "success"
            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
            : "border-red-500/30 bg-red-500/10 text-red-300"
            }`}
        >
          {message.text}
        </div>
      )}

      {/* Restart Warning */}
      {restartRequired.length > 0 && (
        <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/10 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 text-yellow-400" />
            <div>
              <p className="font-semibold text-yellow-300">{t("config.parameters.restartRequired.title")}</p>
              <p className="mt-1 text-sm text-yellow-200">
                {t("config.parameters.restartRequired.message", { services: restartRequired.join(", ") })}
              </p>
              <p className="mt-2 text-xs text-yellow-200/80">
                {t("config.parameters.restartRequired.hint")}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* LLM Runtime Info */}
      <div className="glass-panel rounded-2xl border border-white/10 bg-gradient-to-r from-violet-500/10 to-cyan-500/10 p-6">
        <div className="flex items-start gap-3">
          <Info className="mt-0.5 h-5 w-5 text-cyan-400" />
          <div>
            <h3 className="heading-h3">{t("config.parameters.runtimeInfo.title")}</h3>
            <p className="mt-2 text-sm text-zinc-300">
              {t("config.parameters.runtimeInfo.ollama")}
            </p>
            {vllmAvailableInProfile && (
              <p className="mt-2 text-sm text-zinc-300">
                {t("config.parameters.runtimeInfo.vllm")}
              </p>
            )}
            <p className="mt-3 text-hint">
              {t("config.parameters.runtimeInfo.hint")}{" "}
              <Link href="/benchmark" className="text-emerald-400 hover:underline">
                {t("config.parameters.runtimeInfo.benchmark")}
              </Link>{" "}
            </p>
          </div>
        </div>
      </div>

      {/* AI Mode Section */}
      {renderSection(
        t("config.parameters.sections.aiMode.title"),
        t("config.parameters.sections.aiMode.description"),
        [
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
        ]
      )}

      {/* LLM Server Commands */}
      {renderSection(
        t("config.parameters.sections.commands.title"),
        t("config.parameters.sections.commands.description"),
        [
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
        ]
      )}

      {vllmAvailableInProfile && renderSection(
        t("config.parameters.sections.vllm_advanced.title"),
        t("config.parameters.sections.vllm_advanced.description"),
        [
          "VLLM_MODEL_PATH",
          "VLLM_SERVED_MODEL_NAME",
          "VLLM_GPU_MEMORY_UTILIZATION",
          "VLLM_MAX_BATCHED_TOKENS",
        ]
      )}

      {renderSection(
        t("config.parameters.sections.routing.title"),
        t("config.parameters.sections.routing.description"),
        [
          "ENABLE_CONTEXT_COMPRESSION",
          "MAX_CONTEXT_TOKENS",
        ]
      )}

      {renderSection(
        t(EMBEDDING_ROUTER_SECTION.title),
        t(EMBEDDING_ROUTER_SECTION.description),
        [...EMBEDDING_ROUTER_SECTION.keys]
      )}

      {renderSection(
        t("config.parameters.sections.prompts.title"),
        t("config.parameters.sections.prompts.description"),
        ["PROMPTS_DIR"]
      )}

      {/* Hive Configuration */}
      {renderSection(
        t("config.parameters.sections.hive.title"),
        t("config.parameters.sections.hive.description"),
        [
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
        ]
      )}

      {/* Nexus Configuration */}
      {renderSection(
        t("config.parameters.sections.nexus.title"),
        t("config.parameters.sections.nexus.description"),
        [
          "ENABLE_NEXUS",
          "NEXUS_SHARED_TOKEN",
          "NEXUS_HEARTBEAT_TIMEOUT",
          "NEXUS_PORT",
        ]
      )}

      {/* Background Tasks */}
      {renderSection(
        t("config.parameters.sections.tasks.title"),
        t("config.parameters.sections.tasks.description"),
        [
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
        ]
      )}

      {renderSection(
        t("config.parameters.sections.sandbox.title"),
        t("config.parameters.sections.sandbox.description"),
        ["ENABLE_SANDBOX", "DOCKER_IMAGE_NAME"]
      )}

      {/* Shadow Agent */}
      {renderSection(
        t("config.parameters.sections.shadow.title"),
        t("config.parameters.sections.shadow.description"),
        [
          "ENABLE_PROACTIVE_MODE",
          "ENABLE_DESKTOP_SENSOR",
          "SHADOW_CONFIDENCE_THRESHOLD",
          "SHADOW_PRIVACY_FILTER",
          "SHADOW_CLIPBOARD_MAX_LENGTH",
          "SHADOW_CHECK_INTERVAL",
        ]
      )}

      {/* Ghost Agent */}
      {renderSection(
        t("config.parameters.sections.ghost.title"),
        t("config.parameters.sections.ghost.description"),
        [
          "ENABLE_GHOST_AGENT",
          "GHOST_MAX_STEPS",
          "GHOST_STEP_DELAY",
          "GHOST_VERIFICATION_ENABLED",
          "GHOST_SAFETY_DELAY",
          "GHOST_VISION_CONFIDENCE",
        ]
      )}

      {/* Audio Interface */}
      {renderSection(
        t("config.parameters.sections.avatar.title"),
        t("config.parameters.sections.avatar.description"),
        [
          "ENABLE_AUDIO_INTERFACE",
          "WHISPER_MODEL_SIZE",
          "TTS_MODEL_PATH",
          "AUDIO_DEVICE",
          "VAD_THRESHOLD",
          "SILENCE_DURATION",
        ]
      )}

      {renderSection(
        t("config.parameters.sections.integrations.title"),
        t("config.parameters.sections.integrations.description"),
        [
          "ENABLE_HF_INTEGRATION",
          "HF_TOKEN",
          "GITHUB_TOKEN",
          "GITHUB_REPO_NAME",
          "DISCORD_WEBHOOK_URL",
          "SLACK_WEBHOOK_URL",
          "ENABLE_ISSUE_POLLING",
          "ISSUE_POLLING_INTERVAL_MINUTES",
          "TAVILY_API_KEY",
        ]
      )}

      {renderSection(
        t("config.parameters.sections.calendar.title"),
        t("config.parameters.sections.calendar.description"),
        [
          "ENABLE_GOOGLE_CALENDAR",
          "GOOGLE_CALENDAR_CREDENTIALS_PATH",
          "GOOGLE_CALENDAR_TOKEN_PATH",
          "VENOM_CALENDAR_ID",
          "VENOM_CALENDAR_NAME",
        ]
      )}

      {renderSection(
        t("config.parameters.sections.iot.title"),
        t("config.parameters.sections.iot.description"),
        [
          "ENABLE_IOT_BRIDGE",
          "RIDER_PI_HOST",
          "RIDER_PI_PORT",
          "RIDER_PI_USERNAME",
          "RIDER_PI_PASSWORD",
          "RIDER_PI_KEY_FILE",
          "RIDER_PI_PROTOCOL",
          "IOT_REQUIRE_CONFIRMATION",
        ]
      )}

      {renderSection(
        t("config.parameters.sections.academy.title"),
        t("config.parameters.sections.academy.description"),
        [
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
        ]
      )}

      {renderSection(
        t("config.parameters.sections.simulations.title"),
        t("config.parameters.sections.simulations.description"),
        [
          "ENABLE_SIMULATION",
          "SIMULATION_CHAOS_ENABLED",
          "SIMULATION_MAX_STEPS",
          "SIMULATION_USER_MODEL",
          "SIMULATION_ANALYST_MODEL",
          "SIMULATION_DEFAULT_USERS",
          "SIMULATION_LOGS_DIR",
        ]
      )}

      {renderSection(
        t("config.parameters.sections.launchpad.title"),
        t("config.parameters.sections.launchpad.description"),
        [
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
        ]
      )}

      {renderSection(
        t("config.parameters.sections.dreamer.title"),
        t("config.parameters.sections.dreamer.description"),
        [
          "ENABLE_DREAMING",
          "DREAMING_IDLE_THRESHOLD_MINUTES",
          "DREAMING_NIGHT_HOURS",
          "DREAMING_MAX_SCENARIOS",
          "DREAMING_CPU_THRESHOLD",
          "DREAMING_MEMORY_THRESHOLD",
          "DREAMING_SCENARIO_COMPLEXITY",
          "DREAMING_VALIDATION_STRICT",
        ]
      )}

      {/* Action Buttons */}
      <div className="glass-panel sticky bottom-6 rounded-2xl box-muted p-6 backdrop-blur-xl">
        <div className="flex items-center justify-between">
          <div>
            {hasChanges() && (
              <p className="text-sm text-yellow-300">
                {t("config.parameters.unsavedChanges", { count: getChangedKeys().length })}
              </p>
            )}
          </div>
          <div className="flex gap-3">
            <Button
              onClick={handleReset}
              disabled={!hasChanges() || saving}
              variant="secondary"
            >
              {t("config.parameters.buttons.reset")}
            </Button>
            <Button onClick={handleSave} disabled={!hasChanges() || saving}>
              <Save className="mr-2 h-4 w-4" />
              {saving ? t("config.parameters.buttons.saving") : t("config.parameters.buttons.save")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
