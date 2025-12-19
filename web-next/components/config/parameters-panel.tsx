"use client";

import { useEffect, useId, useState } from "react";
import { Save, Eye, EyeOff, AlertTriangle, Info, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Config {
  [key: string]: string;
}

function ConfigSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const contentId = useId();

  return (
    <div className="glass-panel rounded-2xl border border-white/10 bg-black/20 p-6">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-start justify-between gap-4 text-left"
      >
        <div>
          <h3 className="text-lg font-semibold text-white">{title}</h3>
          <p className="mt-1 text-sm text-zinc-400">{description}</p>
        </div>
        <ChevronDown
          className={`mt-1 h-5 w-5 text-zinc-500 transition-transform duration-300 ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>
      <div
        id={contentId}
        className={`overflow-hidden transition-[max-height,opacity,transform] duration-300 ease-out ${
          open ? "max-h-[1200px] opacity-100 translate-y-0" : "max-h-0 opacity-0 -translate-y-1"
        }`}
      >
        <div className="pt-4 space-y-4">{children}</div>
      </div>
    </div>
  );
}

export function ParametersPanel() {
  const [config, setConfig] = useState<Config>({});
  const [originalConfig, setOriginalConfig] = useState<Config>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(
    null
  );
  const [showSecrets, setShowSecrets] = useState<{ [key: string]: boolean }>({});
  const [restartRequired, setRestartRequired] = useState<string[]>([]);

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/v1/config/runtime");

      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        const errorMessage =
          errorText || `Nie udało się pobrać konfiguracji (HTTP ${response.status})`;
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
      } else {
        const errorMessage = data.message || "Nie udało się pobrać konfiguracji";
        setMessage({
          type: "error",
          text: errorMessage,
        });
      }
    } catch (error) {
      // TODO: Replace with proper error reporting service
      console.error("Błąd pobierania konfiguracji:", error);
      setMessage({
        type: "error",
        text: "Wystąpił błąd podczas pobierania konfiguracji",
      });
    } finally {
      setLoading(false);
    }
  };

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
      setMessage({ type: "error", text: "Brak zmian do zapisania" });
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
        text: error instanceof Error ? error.message : "Błąd komunikacji z API",
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

  const renderInput = (key: string, value: string) => {
    const secret = isSecret(key);
    const showValue = !secret || showSecrets[key];

    return (
      <div key={key} className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-zinc-300">{key}</label>
          {secret && (
            <button
              onClick={() => toggleSecret(key)}
              className="text-xs text-zinc-500 hover:text-zinc-300"
            >
              {showValue ? (
                <EyeOff className="h-4 w-4" />
              ) : (
                <Eye className="h-4 w-4" />
              )}
            </button>
          )}
        </div>
        <input
          type={showValue ? "text" : "password"}
          value={value}
          onChange={(e) => handleChange(key, e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-sm text-white outline-none focus:border-emerald-400 focus:ring-0"
        />
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
        <div className="text-zinc-400">Ładowanie konfiguracji...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Message */}
      {message && (
        <div
          className={`rounded-xl border p-4 ${
            message.type === "success"
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
              <p className="font-semibold text-yellow-300">Restart wymagany</p>
              <p className="mt-1 text-sm text-yellow-200">
                Następujące usługi wymagają restartu:{" "}
                <span className="font-mono">{restartRequired.join(", ")}</span>
              </p>
              <p className="mt-2 text-xs text-yellow-200/80">
                Przejdź do zakładki &quot;Usługi&quot; aby zrestartować odpowiednie
                komponenty.
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
            <h3 className="font-semibold text-white">Runtime LLM: Ollama vs vLLM</h3>
            <p className="mt-2 text-sm text-zinc-300">
              <strong className="text-emerald-300">Ollama (Light):</strong> Priorytet na
              najkrótszy czas pytanie→odpowiedź, niski footprint (single user). Idealny do
              codziennej pracy.
            </p>
            <p className="mt-2 text-sm text-zinc-300">
              <strong className="text-cyan-300">vLLM (Full):</strong> Pipeline benchmarkowy,
              dłuższy start, rezerwuje cały VRAM, ale pozwala na testy wydajności i większą
              przepustowość.
            </p>
            <p className="mt-3 text-xs text-zinc-400">
              💡 Domyślnie uruchamiamy tylko jeden runtime naraz. Druga opcja ma sens jedynie,
              gdy rozdzielamy role (np. UI vs. kodowanie). Pełna strategia wyboru runtime
              będzie oparta na wynikach testów —{" "}
              <a href="/benchmark" className="text-emerald-400 hover:underline">
                przejdź do benchmarków
              </a>{" "}
              aby porównać modele.
            </p>
          </div>
        </div>
      </div>

      {/* AI Mode Section */}
      {renderSection(
        "Tryb AI",
        "Konfiguracja modeli AI: lokalny, hybrydowy lub cloud",
        [
          "AI_MODE",
          "LLM_SERVICE_TYPE",
          "LLM_LOCAL_ENDPOINT",
          "LLM_MODEL_NAME",
          "LLM_LOCAL_API_KEY",
          "OPENAI_API_KEY",
          "GOOGLE_API_KEY",
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
        "Komendy serwera LLM",
        "Komendy do uruchamiania/zatrzymywania serwerów Ollama i vLLM",
        [
          "VLLM_START_COMMAND",
          "VLLM_STOP_COMMAND",
          "OLLAMA_START_COMMAND",
          "OLLAMA_STOP_COMMAND",
        ]
      )}

      {/* Hive Configuration */}
      {renderSection(
        "Hive - Przetwarzanie rozproszone",
        "Konfiguracja architektury rozproszonej z Redis message broker",
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
        "Nexus - Distributed Mesh",
        "Master-Worker architecture dla zdalnych węzłów",
        [
          "ENABLE_NEXUS",
          "NEXUS_SHARED_TOKEN",
          "NEXUS_HEARTBEAT_TIMEOUT",
          "NEXUS_PORT",
        ]
      )}

      {/* Background Tasks */}
      {renderSection(
        "Zadania w tle",
        "Automatyczne zadania: dokumentacja, refaktoryzacja, konsolidacja pamięci",
        [
          "VENOM_PAUSE_BACKGROUND_TASKS",
          "ENABLE_AUTO_DOCUMENTATION",
          "ENABLE_AUTO_GARDENING",
          "ENABLE_MEMORY_CONSOLIDATION",
          "ENABLE_HEALTH_CHECKS",
          "WATCHER_DEBOUNCE_SECONDS",
          "IDLE_THRESHOLD_MINUTES",
        ]
      )}

      {/* Shadow Agent */}
      {renderSection(
        "Shadow - Desktop Awareness",
        "Agent świadomości desktopowej i proaktywnego działania",
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
        "Ghost - Visual GUI Automation",
        "Agent automatyzacji GUI (RPA)",
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
        "Avatar - Audio Interface",
        "Interfejs audio: rozpoznawanie mowy i synteza głosu",
        [
          "ENABLE_AUDIO_INTERFACE",
          "WHISPER_MODEL_SIZE",
          "TTS_MODEL_PATH",
          "AUDIO_DEVICE",
          "VAD_THRESHOLD",
          "SILENCE_DURATION",
        ]
      )}

      {/* Action Buttons */}
      <div className="glass-panel sticky bottom-6 rounded-2xl border border-white/10 bg-black/40 p-6 backdrop-blur-xl">
        <div className="flex items-center justify-between">
          <div>
            {hasChanges() && (
              <p className="text-sm text-yellow-300">
                Masz niezapisane zmiany ({getChangedKeys().length} parametrów)
              </p>
            )}
          </div>
          <div className="flex gap-3">
            <Button
              onClick={handleReset}
              disabled={!hasChanges() || saving}
              variant="secondary"
            >
              Resetuj
            </Button>
            <Button onClick={handleSave} disabled={!hasChanges() || saving}>
              <Save className="mr-2 h-4 w-4" />
              {saving ? "Zapisywanie..." : "Zapisz konfigurację"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
