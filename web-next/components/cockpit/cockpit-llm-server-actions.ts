"use client";

import { useCallback, useEffect } from "react";
import type { ServiceStatus, ActiveLlmServerResponse } from "@/lib/types";

type LlmServerEntry = {
  name: string;
};

type ActiveServerInfo = ActiveLlmServerResponse | null;

type CockpitLlmServerActionsParams = {
  selectedLlmServer: string;
  selectedLlmModel: string;
  setSelectedLlmServer: (value: string) => void;
  setSelectedLlmModel: (value: string) => void;
  setMessage: (value: string | null) => void;
  pushToast: (message: string, tone?: "success" | "warning" | "error" | "info") => void;
  setLlmActionPending: (value: string | null) => void;
  refreshLlmServers: () => void;
  refreshActiveServer: () => void;
  refreshModels: () => void;
  activeServerInfo: ActiveServerInfo;
  llmServers: LlmServerEntry[];
  availableModelsForServer: Array<{ name: string }>;
  serviceStatusMap: Map<string, ServiceStatus>;
  activateRegistryModel: (payload: { name: string; runtime: string }) => Promise<unknown>;
  switchModel: (model: string) => Promise<unknown>;
  setActiveLlmServer: (server: string) => Promise<{ status?: string; active_model?: string | null }>;
};

const isRegistryRuntime = (server: string): boolean => server === "vllm" || server === "ollama";

const resolveActivationError = (err: unknown): string =>
  err instanceof Error ? err.message : "Nie udało się aktywować serwera.";

const resolveLastModelForServer = (
  server: string,
  lastModels?: ActiveLlmServerResponse["last_models"],
): string => {
  if (!lastModels) return "";
  if (server === "ollama") return lastModels.ollama || lastModels.previous_ollama || "";
  if (server === "vllm") return lastModels.vllm || lastModels.previous_vllm || "";
  return "";
};

export function useCockpitLlmServerActions({
  selectedLlmServer,
  selectedLlmModel,
  setSelectedLlmServer,
  setSelectedLlmModel,
  setMessage,
  pushToast,
  setLlmActionPending,
  refreshLlmServers,
  refreshActiveServer,
  refreshModels,
  activeServerInfo,
  llmServers,
  availableModelsForServer,
  serviceStatusMap,
  activateRegistryModel,
  switchModel,
  setActiveLlmServer,
}: CockpitLlmServerActionsParams) {
  const activateModelForServer = useCallback(
    async (server: string, model: string) => {
      if (isRegistryRuntime(server)) {
        await activateRegistryModel({ name: model, runtime: server });
        return;
      }
      await switchModel(model);
    },
    [activateRegistryModel, switchModel],
  );

  const ensureSelectedModel = useCallback(
    (server: string, currentSelection: string) => {
      if (!server || availableModelsForServer.length === 0) return "";
      const availableNames = new Set(availableModelsForServer.map((model) => model.name));
      if (currentSelection && availableNames.has(currentSelection)) return currentSelection;

      const currentActive =
        activeServerInfo?.active_server === server ? activeServerInfo?.active_model ?? "" : "";
      if (currentActive && availableNames.has(currentActive)) return currentActive;

      const lastForServer = resolveLastModelForServer(server, activeServerInfo?.last_models);
      if (lastForServer && availableNames.has(lastForServer)) return lastForServer;

      return availableModelsForServer[0].name;
    },
    [activeServerInfo?.active_model, activeServerInfo?.active_server, activeServerInfo?.last_models, availableModelsForServer],
  );

  const handleLlmServerActivate = useCallback(async (override?: { server?: string; model?: string }) => {
    const targetServer = override?.server ?? selectedLlmServer;
    const targetModel = override?.model ?? selectedLlmModel;
    if (!targetServer) {
      setMessage("Wybierz serwer LLM.");
      pushToast("Wybierz serwer LLM.", "warning");
      return;
    }
    try {
      setLlmActionPending(`activate:${targetServer}`);
      if (targetModel && activeServerInfo?.active_server === targetServer) {
        await activateModelForServer(targetServer, targetModel);
        setMessage(`Aktywowano model ${targetModel} na serwerze ${targetServer}.`);
        pushToast(`Aktywny serwer: ${targetServer}, model: ${targetModel}.`, "success");
        return;
      }
      const response = await setActiveLlmServer(targetServer);
      if (response.status === "success") {
        setMessage(`Aktywowano serwer ${targetServer}.`);
        pushToast(`Aktywny serwer: ${targetServer}.`, "success");
        if (targetModel && response.active_model && response.active_model !== targetModel) {
          await activateModelForServer(targetServer, targetModel);
          setMessage(`Aktywowano serwer ${targetServer} i model ${targetModel}.`);
          pushToast(`Aktywny serwer: ${targetServer}, model: ${targetModel}.`, "success");
        }
      } else {
        setMessage("Nie udało się aktywować serwera.");
        pushToast("Nie udało się aktywować serwera.", "error");
      }
    } catch (err) {
      const message = resolveActivationError(err);
      setMessage(message);
      pushToast(message, "error");
    } finally {
      setLlmActionPending(null);
      refreshLlmServers();
      refreshActiveServer();
      refreshModels();
    }
  }, [
    activeServerInfo?.active_server,
    activateModelForServer,
    pushToast,
    refreshActiveServer,
    refreshLlmServers,
    refreshModels,
    selectedLlmModel,
    selectedLlmServer,
    setActiveLlmServer,
    setLlmActionPending,
    setMessage,
  ]);

  const handleChatModelSelect = useCallback(
    (value: string) => {
      if (!value) return;
      handleLlmServerActivate({ model: value });
    },
    [handleLlmServerActivate],
  );

  const resolveServerStatus = useCallback(
    (serverName: string, fallback?: string | null) => {
      const lowered = serverName.toLowerCase();
      const match =
        serviceStatusMap.get(lowered) ||
        serviceStatusMap.get(serverName.toLowerCase());
      return (fallback || match?.status || "unknown").toLowerCase();
    },
    [serviceStatusMap],
  );

  useEffect(() => {
    if (!selectedLlmServer && activeServerInfo?.active_server) {
      setSelectedLlmServer(activeServerInfo.active_server);
    }
  }, [activeServerInfo?.active_server, selectedLlmServer, setSelectedLlmServer]);

  useEffect(() => {
    if (selectedLlmServer) return;
    if (activeServerInfo?.active_server) {
      setSelectedLlmServer(activeServerInfo.active_server);
      return;
    }
    if (llmServers.length > 0) {
      setSelectedLlmServer(llmServers[0].name);
    }
  }, [activeServerInfo?.active_server, llmServers, selectedLlmServer, setSelectedLlmServer]);

  useEffect(() => {
    if (!selectedLlmServer) {
      setSelectedLlmModel("");
      return;
    }
    const preferred = ensureSelectedModel(selectedLlmServer, selectedLlmModel);
    if (!preferred) {
      setSelectedLlmModel("");
      return;
    }
    if (preferred === selectedLlmModel) return;
    setSelectedLlmModel(preferred);
  }, [
    ensureSelectedModel,
    selectedLlmModel,
    selectedLlmServer,
    setSelectedLlmModel,
  ]);

  useEffect(() => {
    if (!selectedLlmServer) return;
    if (availableModelsForServer.length !== 1) return;
    const soleModel = availableModelsForServer[0]?.name;
    if (!soleModel) return;
    if (
      activeServerInfo?.active_server === selectedLlmServer &&
      activeServerInfo?.active_model === soleModel
    ) {
      return;
    }
    handleLlmServerActivate({ server: selectedLlmServer, model: soleModel });
  }, [
    activeServerInfo?.active_model,
    activeServerInfo?.active_server,
    availableModelsForServer,
    handleLlmServerActivate,
    selectedLlmServer,
  ]);

  useEffect(() => {
    if (!selectedLlmServer) return;
    refreshModels();
    refreshActiveServer();
  }, [refreshActiveServer, refreshModels, selectedLlmServer]);

  return { handleChatModelSelect, handleLlmServerActivate, resolveServerStatus };
}
