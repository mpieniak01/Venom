"use client";
import { useLanguage } from "@/lib/i18n";
import { useOpenRouterCatalog, OpenRouterModelStatus } from "@/components/cockpit/openrouter-model-status";
import type { UnifiedModelCatalogResponse } from "@/lib/academy-api";
import type { ConversationInteraction } from "./use-conversation-controller";
export function StudioModelPicker({ catalog, interaction, session, activeModel, onApply, busy }: Readonly<{
  catalog: UnifiedModelCatalogResponse | null; interaction: ConversationInteraction; session: string;
  activeModel: string | null | undefined; onApply: (model: string) => Promise<boolean>; busy: boolean;
}>) {
  const { t } = useLanguage();
  const { state, setters } = interaction;
  const runtime = catalog?.runtimes.find(item => item.runtime_id === state.selectedLlmServer);
  const models = (runtime?.models ?? []).filter(item => item.chat_compatible !== false && item.model_kind !== "adapter_artifact" && !item.is_adapter_artifact);
  const remote = ["openrouter", "vast_ollama"].includes(state.selectedLlmServer);
  const openrouter = useOpenRouterCatalog(state.selectedLlmServer === "openrouter");
  return <section className="studio-models" aria-label={t("chat2.engine")}>
    <div className="studio-model-line">
      <label>{t("chat2.engine")}<select aria-label={t("chat2.engine")} value={state.selectedLlmServer} disabled={busy}
        onChange={event => setters.setSelectedLlmServer(event.target.value)}>
        {!runtime && <option value={state.selectedLlmServer}>{state.selectedLlmServer || t("chat2.unknown")}</option>}
        {catalog?.runtimes.map(item => <option key={item.runtime_id} value={item.runtime_id} disabled={!item.configured}>{item.label || item.display_name || item.runtime_id}</option>)}
      </select></label>
      <label className="studio-model-select">{t("chat2.model")}<select aria-label={t("chat2.model")} value={state.selectedLlmModel} disabled={busy}
        onChange={event => setters.setSelectedLlmModel(event.target.value)}>
        {!models.some(item => item.name === state.selectedLlmModel) && <option value={state.selectedLlmModel}>{state.selectedLlmModel || t("chat2.unknown")}</option>}
        {models.map(item => <option key={item.id} value={item.name || item.id}>{item.name || item.id}</option>)}
      </select></label>
      <button type="button" className="studio-button" disabled={busy || !state.selectedLlmModel}
        onClick={() => { void onApply(state.selectedLlmModel); }}>{t("chat2.apply")}</button>
      <label>{t("chat2.mode")}<select aria-label={t("chat2.mode")} value={state.chatMode} disabled={busy}
        onChange={event => setters.setChatMode(event.target.value as "direct" | "normal" | "complex")}>
        <option value="direct">{t("chat2.direct")}</option>
        <option value="normal" disabled={remote}>{t("chat2.normal")}</option>
        <option value="complex" disabled={remote}>{t("chat2.complex")}</option>
      </select></label>
    </div>
    <div className="studio-model-info">
      <span className="studio-dot" /> <span>{runtime?.source_type === "local-runtime" ? t("chat2.local") : runtime ? t("chat2.remote") : t("chat2.unknown")}</span>
      <span>{t("chat2.activeModel")}: {activeModel || t("chat2.unknown")}</span>
      <details><summary>{t("chat2.costs")}</summary><div className="studio-detail-card">
        {state.selectedLlmServer === "openrouter" ? <OpenRouterModelStatus selection={openrouter} model={state.selectedLlmModel} session={session} /> : <p>{t("chat2.noPrice")}</p>}
      </div></details>
    </div>
  </section>;
}
