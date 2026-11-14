"use client";

import { useEffect, useState } from "react";
import { listTrainingModelSpecs, type TrainingModelSpec } from "@/lib/academy-experiments-api";
import { useTranslation } from "@/lib/i18n";

const STATUSES: Record<string, string> = {
  local_gpu_executor_available: "local",
  trained_candidate_below_acceptance: "candidate",
  remote_gpu_smoke_required: "smoke",
};

export function ModelTrainingSpecs() {
  const t = useTranslation();
  const [models, setModels] = useState<TrainingModelSpec[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const abort = new AbortController();
    void listTrainingModelSpecs(abort.signal)
      .then((items) => { if (!abort.signal.aborted) setModels(items); })
      .catch(() => { if (!abort.signal.aborted) setFailed(true); });
    return () => abort.abort();
  }, []);

  if (failed) return <p role="alert" className="text-sm text-red-400">{t("academy.experiments.modelSpecs.loadError")}</p>;
  if (!models.length) return null;

  return (
    <section className="space-y-2" aria-label={t("academy.experiments.modelSpecs.title")}>
      <h4 className="font-medium">{t("academy.experiments.modelSpecs.title")}</h4>
      <p className="text-sm text-hint">{t("academy.experiments.modelSpecs.intro")}</p>
      <div className="grid gap-3 lg:grid-cols-3">
        {models.map((model) => {
          const status = STATUSES[model.status];
          const memory = typeof model.gpu_memory === "string"
            ? t("academy.experiments.modelSpecs.measured")
            : `${model.gpu_memory.shared_lora_qlora.gpu_memory_gb} GB (${t("academy.experiments.modelSpecs.estimate")})`;
          const runtime = typeof model.runtime === "string"
            ? t("academy.experiments.modelSpecs.localRuntime")
            : `Python ${model.runtime.python} · ${Object.entries(model.runtime.versions).map(([name, version]) => `${name} ${version}`).join(" · ")}`;
          return (
            <details key={model.model} className="rounded-md border border-[color:var(--ui-border)] p-3 text-sm">
              <summary className="cursor-pointer font-medium break-words">{model.model}</summary>
              <p className="mt-2">{status ? t(`academy.experiments.modelSpecs.status.${status}`) : model.status}</p>
              <dl className="mt-2 space-y-1">
                <div><dt className="text-hint">{t("academy.experiments.modelSpecs.loader")}</dt><dd>{model.loader}</dd></div>
                <div><dt className="text-hint">{t("academy.experiments.modelSpecs.revision")}</dt><dd className="break-all">{model.revision}</dd></div>
                <div><dt className="text-hint">LoRA</dt><dd>{model.target_families.join(", ")}</dd></div>
                <div><dt className="text-hint">{t("academy.experiments.modelSpecs.modality")}</dt><dd>{t(`academy.experiments.modelSpecs.contract.${model.modality}`)}</dd></div>
                <div><dt className="text-hint">{t("academy.experiments.modelSpecs.data")}</dt><dd>{t(`academy.experiments.modelSpecs.contract.${model.data_contract}`)}</dd></div>
                <div><dt className="text-hint">GPU</dt><dd>{memory}</dd></div>
                <div><dt className="text-hint">{t("academy.experiments.modelSpecs.runtime")}</dt><dd className="break-words">{runtime}</dd></div>
                <div><dt className="text-hint">{t("academy.experiments.modelSpecs.defaults")}</dt><dd className="break-words">{Object.entries(model.recipe_defaults).map(([key, value]) => `${key}=${value}`).join(" · ")}</dd></div>
                <div><dt className="text-hint">{t("academy.experiments.modelSpecs.qualification")}</dt><dd>{t(`academy.experiments.modelSpecs.contract.${model.qualification}`)}</dd></div>
              </dl>
            </details>
          );
        })}
      </div>
    </section>
  );
}
