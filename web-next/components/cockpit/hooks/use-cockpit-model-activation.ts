"use client";

type ModelDef = { name: string; provider?: string };

export function useCockpitModelActivation(input: {
  selectedLlmServer: string;
  activeServer: string;
  models: ModelDef[] | undefined;
  setSelectedLlmModel: (model: string) => void;
  setActiveLlmRuntimeFn: (provider: string, model: string) => Promise<unknown>;
  setActiveLlmServerFn: (provider: string) => Promise<unknown>;
  switchModelFn: (model: string) => Promise<unknown>;
  refreshActiveServer: () => void;
  pushToast: (message: string, type?: "success" | "error" | "warning") => void;
  t: (key: string, replacements?: Record<string, string | number>) => string;
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
    t,
  } = input;

  const handleActivateModel = async (model: string) => {
    setSelectedLlmModel(model);

    let provider = selectedLlmServer || activeServer;
    const modelDef = models?.find((m) => m.name === model);
    if (modelDef?.provider) {
      provider = modelDef.provider;
    }

    if (!provider) {
      pushToast(t("cockpit.modelActivation.providerMissing"), "warning");
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

      pushToast(t("cockpit.modelActivation.activated", { model }), "success");
      refreshActiveServer();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("cockpit.modelActivation.unknownError");
      pushToast(t("cockpit.modelActivation.failed", { message }), "error");
    }
  };

  return { handleActivateModel };
}
