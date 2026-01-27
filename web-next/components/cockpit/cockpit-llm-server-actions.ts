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
        if (targetServer === "vllm" || targetServer === "ollama") {
          await activateRegistryModel({ name: targetModel, runtime: targetServer });
        } else {
          await switchModel(targetModel);
        }
        setMessage(`Aktywowano model ${targetModel} na serwerze ${targetServer}.`);
        pushToast(`Aktywny serwer: ${targetServer}, model: ${targetModel}.`, "success");
        return;
      }
      const response = await setActiveLlmServer(targetServer);
      if (response.status === "success") {
        setMessage(`Aktywowano serwer ${targetServer}.`);
        pushToast(`Aktywny serwer: ${targetServer}.`, "success");
        if (targetModel && response.active_model && response.active_model !== targetModel) {
          if (targetServer === "vllm" || targetServer === "ollama") {
            await activateRegistryModel({ name: targetModel, runtime: targetServer });
          } else {
            await switchModel(targetModel);
          }
          setMessage(`Aktywowano serwer ${targetServer} i model ${targetModel}.`);
          pushToast(`Aktywny serwer: ${targetServer}, model: ${targetModel}.`, "success");
        }
      } else {
        setMessage("Nie udało się aktywować serwera.");
        pushToast("Nie udało się aktywować serwera.", "error");
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Nie udało się aktywować serwera.");
      pushToast(err instanceof Error ? err.message : "Nie udało się aktywować serwera.", "error");
    } finally {
      setLlmActionPending(null);
      refreshLlmServers();
      refreshActiveServer();
      refreshModels();
    }
  }, [
    activeServerInfo?.active_server,
    activateRegistryModel,
    pushToast,
    refreshActiveServer,
    refreshLlmServers,
    refreshModels,
    selectedLlmModel,
    selectedLlmServer,
    setActiveLlmServer,
    setLlmActionPending,
    setMessage,
    switchModel,
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
    if (availableModelsForServer.length === 0) {
      setSelectedLlmModel("");
      return;
    }
    const currentActive =
      activeServerInfo?.active_server === selectedLlmServer
        ? activeServerInfo?.active_model ?? ""
        : "";
    const lastModels = activeServerInfo?.last_models ?? {};
    const lastForServer =
      selectedLlmServer === "ollama"
        ? lastModels.ollama || lastModels.previous_ollama
        : selectedLlmServer === "vllm"
          ? lastModels.vllm || lastModels.previous_vllm
          : "";
    const availableNames = new Set(
      availableModelsForServer.map((model) => model.name),
    );
    if (selectedLlmModel && availableNames.has(selectedLlmModel)) {
      return;
    }
    if (currentActive && availableNames.has(currentActive)) {
      setSelectedLlmModel(currentActive);
      return;
    }
    if (lastForServer && availableNames.has(lastForServer)) {
      setSelectedLlmModel(lastForServer);
      return;
    }
    setSelectedLlmModel(availableModelsForServer[0].name);
  }, [
    activeServerInfo?.active_model,
    activeServerInfo?.active_server,
    activeServerInfo?.last_models,
    availableModelsForServer,
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
