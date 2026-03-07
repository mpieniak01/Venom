"use client";

export function useCockpitModelActivation(input: {
  selectedLlmServer: string;
  selectedLlmModel: string;
  activeServer: string;
  setSelectedLlmModel: (model: string) => void;
  setActiveLlmRuntimeFn: (provider: string, model: string) => Promise<unknown>;
  setActiveLlmServerFn: (provider: string, model?: string) => Promise<unknown>;
  refreshActiveServer: () => void;
  pushToast: (message: string, type?: "success" | "error" | "warning") => void;
  t: (key: string, replacements?: Record<string, string | number>) => string;
}) {
  const {
    selectedLlmServer,
    selectedLlmModel,
    activeServer,
    setSelectedLlmModel,
    setActiveLlmRuntimeFn,
    setActiveLlmServerFn,
    refreshActiveServer,
    pushToast,
    t,
  } = input;

  const handleActivateModel = async (model: string): Promise<boolean> => {
    const previousModel = selectedLlmModel || "";
    setSelectedLlmModel(model);

    const provider = selectedLlmServer || activeServer;

    if (!provider) {
      pushToast(t("cockpit.modelActivation.providerMissing"), "warning");
      setSelectedLlmModel(previousModel);
      return false;
    }

    try {
      if (provider === "openai" || provider === "google") {
        await setActiveLlmRuntimeFn(provider, model);
      } else {
        // Local runtimes must switch runtime+model atomically to avoid stale model 404.
        await setActiveLlmServerFn(provider, model);
      }

      pushToast(t("cockpit.modelActivation.activated", { model }), "success");
      refreshActiveServer();
      return true;
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("cockpit.modelActivation.unknownError");
      pushToast(t("cockpit.modelActivation.failed", { message }), "error");
      setSelectedLlmModel(previousModel);
      return false;
    }
  };

  return { handleActivateModel };
}
