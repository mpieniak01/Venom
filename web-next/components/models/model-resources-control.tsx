"use client";

import { Button } from "@/components/ui/button";
import type { ModelResourcesMemory, ModelResourcesResult } from "@/hooks/use-api";

type Props = {
  releasing: boolean;
  memory?: ModelResourcesMemory;
  result: ModelResourcesResult | null;
  entries?: ModelResourcesResult["runtimes"];
  error: string | null;
  onRelease: () => Promise<void>;
  onRecoverLlm?: () => Promise<void>;
  t: (key: string) => string;
};

export function ModelResourcesControl({ releasing, memory, result, entries = result?.runtimes ?? [], error, onRelease, onRecoverLlm, t }: Readonly<Props>) {
  const observed = memory ?? result?.memory_after;
  const grouped = [...entries.reduce((groups, row) => {
    const previous = groups.get(row.runtime);
    groups.set(row.runtime, { ...row, verified: row.verified && (previous?.verified ?? true) });
    return groups;
  }, new Map<string, ModelResourcesResult["runtimes"][number]>()).values()];
  return <section data-testid="global-model-resources" className="rounded-2xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 className="font-semibold">{t("models.resources.title")}</h2>
      </div>
      {onRecoverLlm && <Button variant="secondary" size="sm" disabled={releasing} onClick={() => void onRecoverLlm()} data-testid="recover-llm">{t("models.resources.recoverLlm")}</Button>}
      <Button variant="secondary" size="sm" disabled={releasing} onClick={() => void onRelease()} data-testid="release-all-models">
        {t(releasing ? "models.resources.releasing" : "models.resources.release")}
      </Button>
    </div>
    <div className="mt-3 flex flex-wrap gap-4 text-sm" aria-live="polite">
      {observed && <span>{t("models.resources.ram")}: {observed.rss_mib.toFixed(0)} MiB</span>}
      {observed?.gpu.map(gpu => <span key={gpu.index}>GPU {gpu.index} · VRAM {gpu.used_mib} / {gpu.total_mib} MiB</span>)}
      {observed?.gpu.length === 0 && <span>{t("models.resources.noGpuReading")}</span>}
    </div>
    <output className="mt-2 block text-sm">
      {releasing && t("models.resources.releasing")}
      {error && <span className="text-red-400">{error}</span>}
      {!releasing && !error && result?.released && <span className="text-emerald-400">{t("models.resources.released")}</span>}
    </output>
    {entries.length > 0 && <div className="mt-2 flex flex-wrap gap-2 text-xs" data-testid="resource-release-results">
      {grouped.map((entry, index) => <span key={entry.runtime + index} className={entry.verified ? "text-emerald-400" : "text-red-400"}>
        {entry.verified ? "✓" : "×"} {t("models.resources.categories." + entry.runtime)}
      </span>)}
    </div>}
  </section>;
}
