"use client";

type ModelDef = { name: string; provider?: string };

export function useCockpitModelActivation(input: {
  selectedLlmServer: string;
  activeServer: string;
  models: ModelDef[] | undefined;
  setSelectedLlmModel: (model: string) => void;
  setActiveLlmRuntimeFn: (provider: string, model: string) => Promise<void>;
  setActiveLlmServerFn: (provider: string) => Promise<void>;
  switchModelFn: (model: string) => Promise<void>;
  refreshActiveServer: () => void;
  pushToast: (message: string, type?: "success" | "error" | "warning") => void;
}) {
  const {
    selectedLlmServer,
    activeServer,
    models,
    setSelectedLlmModel,
    setActiveLlmRuntimeFn,
    setActiveLlmServerFn,
    switchModelFn,
    refreshActiveServer,
    pushToast,
  } = input;

  const handleActivateModel = async (model: string) => {
    setSelectedLlmModel(model);

    let provider = selectedLlmServer || activeServer;
    const modelDef = models?.find((m) => m.name === model);
    if (modelDef?.provider) {
      provider = modelDef.provider;
    }

    if (!provider) {
      pushToast("Nie można ustalić serwera dla wybranego modelu.", "warning");
      return;
    }

    try {
      if (provider === "openai" || provider === "google") {
        await setActiveLlmRuntimeFn(provider, model);
      } else {
        if (provider !== activeServer) {
          await setActiveLlmServerFn(provider);
        }
        await switchModelFn(model);
      }

      pushToast(`Aktywowano model: ${model}`, "success");
      refreshActiveServer();
    } catch (err) {
      pushToast(`Błąd aktywacji modelu: ${(err as Error).message}`, "error");
    }
  };

  return { handleActivateModel };
}
