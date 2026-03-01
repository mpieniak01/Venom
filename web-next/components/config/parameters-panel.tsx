"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "@/lib/i18n";
import { ConfigSection } from "./config-section";
import { ParameterInputRow } from "./parameter-input-row";
import { getParametersSections } from "./parameters-sections";
import {
  ParametersActionBar,
  ParametersMessage,
  RestartRequiredNotice,
  RuntimeInfoCard,
} from "./parameters-panel-ui";

interface Config {
  [key: string]: string;
}

interface ConfigSources {
  [key: string]: "env" | "default";
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
        setMessage({ type: "error", text: errorMessage });
        return;
      }

      const data = await response.json();
      if (data.status === "success") {
        setConfig(data.config);
        setOriginalConfig(data.config);
        setConfigSources(data.config_sources || {});
      } else {
        setMessage({
          type: "error",
          text: data.message || t("config.parameters.messages.fetchError"),
        });
      }
    } catch (error) {
      console.error("Błąd pobierania konfiguracji:", error);
      setMessage({ type: "error", text: t("config.parameters.messages.fetchError") });
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchConfig().catch((error) => {
      console.error("Failed to fetch runtime config:", error);
    });
  }, [fetchConfig]);

  const handleChange = (key: string, value: string) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
  };

  const toggleSecret = (key: string) => {
    setShowSecrets((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const changedKeys = useMemo(
    () => Object.keys(config).filter((key) => config[key] !== originalConfig[key]),
    [config, originalConfig]
  );
  const hasChanges = changedKeys.length > 0;

  const handleSave = async () => {
    if (!hasChanges) {
      setMessage({ type: "error", text: t("config.parameters.messages.noChanges") });
      return;
    }

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

  const isSecret = (key: string) =>
    key.includes("KEY") || key.includes("TOKEN") || key.includes("PASSWORD");

  const runtimeProfile = (config.VENOM_RUNTIME_PROFILE || "full").toLowerCase();
  const vllmAvailableInProfile = runtimeProfile === "full";

  const sections = useMemo(
    () => getParametersSections({ t, vllmAvailableInProfile }),
    [t, vllmAvailableInProfile]
  );

  if (loading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="text-hint">{t("config.parameters.loading")}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <ParametersMessage message={message} />

      <RestartRequiredNotice t={t} restartRequired={restartRequired} />

      <RuntimeInfoCard t={t} vllmAvailableInProfile={vllmAvailableInProfile} />

      {sections.map((section) => {
        const sectionKeys = section.keys.filter((key) => Object.hasOwn(config, key));
        if (sectionKeys.length === 0) return null;
        return (
          <ConfigSection key={section.title} title={section.title} description={section.description}>
            {sectionKeys.map((key) => {
              const secret = isSecret(key);
              const showValue = !secret || !!showSecrets[key];
              const valueSource = configSources[key] || "env";
              return (
                <ParameterInputRow
                  key={key}
                  t={t}
                  keyName={key}
                  value={config[key] || ""}
                  valueSource={valueSource}
                  secret={secret}
                  showValue={showValue}
                  onToggleSecret={() => toggleSecret(key)}
                  onChange={(value) => handleChange(key, value)}
                />
              );
            })}
          </ConfigSection>
        );
      })}

      <ParametersActionBar
        t={t}
        hasChanges={hasChanges}
        changedCount={changedKeys.length}
        saving={saving}
        onReset={handleReset}
        onSave={handleSave}
      />
    </div>
  );
}
