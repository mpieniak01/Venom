"use client";

import { useCallback, useEffect, useState } from "react";
import { VenomWebSocket } from "@/lib/ws-client";
import { useLanguage, useTranslation } from "@/lib/i18n";
import type {
  ActionHistory,
  ServiceEvent,
  ServiceInfo,
  StorageSnapshot,
} from "./services-panel-types";
import { applyServiceEventUpdate } from "./services-panel-utils";
import {
  ServicesGrid,
  ServicesHistoryCard,
  ServicesProfilesCard,
  ServicesStorageCard,
} from "./services-panel-ui";

export function ServicesPanel() {
  const t = useTranslation();
  const { language } = useLanguage();
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [servicesLoading, setServicesLoading] = useState(true);
  const [history, setHistory] = useState<ActionHistory[]>([]);
  const [storageSnapshot, setStorageSnapshot] = useState<StorageSnapshot | null>(null);
  const [storageLoading, setStorageLoading] = useState(false);
  const [storageError, setStorageError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(
    null
  );

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/runtime/status").catch((error) => {
        console.warn("Błąd sieci przy pobieraniu statusu usług:", error);
        setMessage({ type: "error", text: t("config.services.status.apiStatusError") });
        return null;
      });
      if (!response) return;
      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        const errorMessage =
          errorText || `${t("config.services.status.apiStatusError")} (HTTP ${response.status})`;
        setMessage({ type: "error", text: errorMessage });
        return;
      }
      const data = await response.json();
      if (data.status === "success") {
        setServices(data.services);
      } else {
        setMessage({
          type: "error",
          text: data.message || t("config.services.status.apiStatusError"),
        });
      }
    } catch (error) {
      console.warn("Błąd pobierania statusu:", error);
      setMessage({ type: "error", text: t("config.services.status.apiStatusError") });
    } finally {
      setServicesLoading(false);
    }
  }, [t]);

  const fetchHistory = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/runtime/history?limit=10").catch((error) => {
        console.warn("Błąd sieci przy pobieraniu historii akcji:", error);
        setMessage({ type: "error", text: t("config.services.history.apiHistoryError") });
        return null;
      });
      if (!response) return;
      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        const errorMessage =
          errorText || `${t("config.services.history.apiHistoryError")} (HTTP ${response.status})`;
        setMessage({ type: "error", text: errorMessage });
        return;
      }
      const data = await response.json();
      if (data.status === "success") {
        setHistory(data.history);
      } else {
        setMessage({
          type: "error",
          text: data.message || t("config.services.history.apiHistoryError"),
        });
      }
    } catch (error) {
      console.error("Błąd pobierania historii:", error);
      setMessage({ type: "error", text: t("config.services.history.apiHistoryError") });
    }
  }, [t]);

  const fetchStorageSnapshot = useCallback(async () => {
    setStorageLoading(true);
    setStorageError(null);
    try {
      const response = await fetch("/api/v1/system/storage").catch(() => {
        setStorageError(t("config.services.storage.apiError"));
        return null;
      });
      if (!response) return;
      if (!response.ok) {
        const errorText = await response.text().catch(() => "");
        const errorMessage =
          errorText || `${t("config.services.storage.apiError")} (HTTP ${response.status})`;
        setStorageError(errorMessage);
        return;
      }
      const data = (await response.json()) as { status?: string } & StorageSnapshot & {
        message?: string;
      };
      if (data.status === "success") {
        setStorageSnapshot(data);
      } else {
        setStorageError(data.message || t("config.services.storage.apiError"));
      }
    } catch (error) {
      setStorageError(
        error instanceof Error ? error.message : t("config.services.storage.apiError")
      );
    } finally {
      setStorageLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void fetchStatus();
    void fetchHistory();
    void fetchStorageSnapshot();

    const ws = new VenomWebSocket("/ws/events", (payload: unknown) => {
      const event = payload as ServiceEvent;
      if (event.type === "SERVICE_STATUS_UPDATE" && event.data && event.data.name) {
        setServices((prevServices) =>
          applyServiceEventUpdate(
            prevServices,
            event.data as Partial<ServiceInfo> & { status: string; name?: string }
          )
        );
      }
    });

    ws.connect();
    const interval = setInterval(() => void fetchStatus(), 10000);
    return () => {
      clearInterval(interval);
      ws.disconnect();
    };
  }, [fetchStatus, fetchHistory, fetchStorageSnapshot]);

  const executeAction = async (service: string, action: string) => {
    const actionKey = `${service}-${action}`;
    setActionInProgress(actionKey);
    setMessage(null);
    try {
      const response = await fetch(`/api/v1/runtime/${service}/${action}`, {
        method: "POST",
      });
      const data = await response.json();
      setMessage({
        type: data.success ? "success" : "error",
        text: data.message,
      });
      await Promise.all([fetchStatus(), fetchHistory()]);
    } catch (error) {
      setMessage({
        type: "error",
        text:
          error instanceof Error ? error.message : t("config.services.status.apiStatusError"),
      });
    } finally {
      setActionInProgress(null);
    }
  };

  const applyProfile = async (profileName: string) => {
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch(`/api/v1/runtime/profile/${profileName}`, {
        method: "POST",
      });
      const data = await response.json();
      setMessage({
        type: data.success ? "success" : "error",
        text: data.message,
      });
      await Promise.all([fetchStatus(), fetchHistory()]);
    } catch (error) {
      setMessage({
        type: "error",
        text:
          error instanceof Error ? error.message : t("config.services.status.apiStatusError"),
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {message ? (
        <div className={`alert ${message.type === "success" ? "alert--success" : "alert--error"}`}>
          {message.text}
        </div>
      ) : null}

      <ServicesProfilesCard t={t} loading={loading} applyProfile={applyProfile} />

      <ServicesGrid
        t={t}
        servicesLoading={servicesLoading}
        services={services}
        actionInProgress={actionInProgress}
        loading={loading}
        executeAction={executeAction}
      />

      <ServicesStorageCard
        t={t}
        language={language}
        storageSnapshot={storageSnapshot}
        storageLoading={storageLoading}
        storageError={storageError}
        onRefreshStorage={fetchStorageSnapshot}
      />

      <ServicesHistoryCard t={t} language={language} history={history} />
    </div>
  );
}
