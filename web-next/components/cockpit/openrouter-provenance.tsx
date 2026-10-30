import type {HistoryRequestDetail} from "@/lib/types";

/** Rows inside the existing model details; every value is whitelisted at stream ingestion. */
export function OpenRouterProvenance({detail,t}: Readonly<{
  detail: HistoryRequestDetail; t: (key:string,values?:Record<string,string|number>)=>string;
}>) {
  if (!detail.openrouter_metadata) return null;
  return <>
    {Object.entries(detail.openrouter_metadata).map(([key,value])=><div key={key}>
      <span className="block text-theme-muted">{t("cockpit.openrouter.provenance."+key)}</span>
      <span>{value??t("cockpit.openrouter.unknown")}</span>
    </div>)}
    <div data-testid="openrouter-upstream-usage">
      <span className="block text-theme-muted">{t("cockpit.openrouter.upstreamUsage")}</span>
      <span>{t("cockpit.openrouter.usageValues",{
        input:detail.openrouter_usage?.prompt_tokens??t("cockpit.openrouter.unknown"),
        output:detail.openrouter_usage?.completion_tokens??t("cockpit.openrouter.unknown"),
        total:detail.openrouter_usage?.total_tokens??t("cockpit.openrouter.unknown"),
      })}</span>
    </div>
  </>;
}
