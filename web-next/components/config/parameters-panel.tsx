"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "@/lib/i18n";
import Link from "next/link";
import { configHref, type useConfigNavigation } from "@/lib/config-navigation";
import { IntegrationLinks } from "./integration-links";
import { useIntegrationInventory } from "@/lib/integration-inventory";
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

export function ParametersPanel({ active = true, navigation }: { active?: boolean; navigation?: ReturnType<typeof useConfigNavigation> } = {}) {
  const t = useTranslation();
  const [localQuery, setLocalQuery] = useState("");
  const query = navigation?.query ?? localQuery;
  const focusedKey = navigation?.parameter ?? null;
  const { data: inventory } = useIntegrationInventory(active);
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
    ["KEY", "TOKEN", "PASSWORD", "SECRET", "CREDENTIAL", "WEBHOOK"].some((part) => key.includes(part));

  const runtimeProfile = (config.VENOM_RUNTIME_PROFILE || "full").toLowerCase();
  const vllmAvailableInProfile = runtimeProfile === "full";

  const sections = useMemo(
    () => {
      const known = getParametersSections({ t, vllmAvailableInProfile });
      const declared = new Set(known.flatMap((section) => section.keys));
      return [...known, { title: t("config.navigation.otherParameters"), description: t("config.navigation.otherParametersDescription"), keys: Object.keys(config).filter((key) => !declared.has(key)) }];
    },
    [t, vllmAvailableInProfile, config]
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
      <label className="block space-y-1 text-sm">
        <span>{t("config.navigation.searchParameters")}</span>
        <input type="search" maxLength={120} value={query} onChange={(event) => navigation ? navigation.navigate({ query: event.target.value, parameter: null }, true) : setLocalQuery(event.target.value)} className="w-full rounded-lg border border-theme bg-theme-overlay p-3 sm:max-w-lg" />
      </label>
      {focusedKey && <div className="flex flex-wrap items-center gap-3 rounded-xl border border-theme p-3 text-sm">
        <span>{focusedKey}</span>
        {!Object.hasOwn(config, focusedKey) && <span role="status">{t("config.navigation.missingParameter")}</span>}
        <button className="underline" onClick={() => navigation?.navigate({ parameter: null })}>{t("config.navigation.allParameters")}</button>
        <IntegrationLinks parameter={focusedKey} active={false} />
      </div>}
      <p className="text-sm text-theme-muted">{t("config.navigation.parameterSearchHint")}</p>

      <RestartRequiredNotice t={t} restartRequired={restartRequired} />

      <RuntimeInfoCard t={t} vllmAvailableInProfile={vllmAvailableInProfile} />

      {sections.map((section) => {
        const sectionKeys = section.keys.filter((key) => Object.hasOwn(config, key)
          && (!focusedKey || key === focusedKey)
          && `${key} ${section.title} ${section.description}`.toLowerCase().includes(query.toLowerCase().trim()));
        if (sectionKeys.length === 0) return null;
        return (
          <ConfigSection key={section.title} title={section.title} description={section.description} forceOpen={Boolean(focusedKey || query.trim())}>
            {section.keys.includes("ENABLE_IOT_BRIDGE") && <p className="mb-4 rounded-lg border border-theme p-3 text-sm text-theme-muted">{t("config.navigation.legacyIotExplanation")}</p>}
            {sectionKeys.map((key) => {
              const secret = isSecret(key);
              const showValue = !secret || !!showSecrets[key];
              const valueSource = configSources[key] || "env";
              return (
                <div key={key} id={`parameter-${key}`} className="space-y-2">
                <ParameterInputRow
                  t={t}
                  keyName={key}
                  value={config[key] || ""}
                  valueSource={valueSource}
                  secret={secret}
                  showValue={showValue}
                  onToggleSecret={() => toggleSecret(key)}
                  onChange={(value) => handleChange(key, value)}
                />
                <nav className="flex flex-wrap gap-3 text-xs" aria-label={t("config.navigation.relatedIntegrations")}>
                  {(inventory?.integrations ?? []).filter((entry) => entry.configuration_keys?.includes(key)).map((entry) => <Link key={entry.id} className="underline" href={configHref({ tab: "integrations", integration: entry.id, visibility: "all", query: "" }, navigation?.search)}>{entry.label}</Link>)}
                </nav>
                </div>
              );
            })}
          </ConfigSection>
        );
      })}

      {!sections.some((section) => section.keys.some((key) => Object.hasOwn(config, key) && (!focusedKey || key === focusedKey) && `${key} ${section.title} ${section.description}`.toLowerCase().includes(query.toLowerCase().trim()))) && <p role="status">{t("config.navigation.noParameters")}</p>}
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
