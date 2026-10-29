import type { OpenRouterCost as Cost } from "@/lib/openrouter-chat";

/** Show unknown/pending accounting explicitly even when an interrupted turn has no usage. */
export function OpenRouterCost({cost, t}: Readonly<{
  cost: Cost; t: (key: string, values?: Record<string, string | number>) => string;
}>) {
  return <section data-testid="openrouter-cost" className="space-y-1 text-sm">
    <h3>{t("cockpit.openrouter.costTitle")}</h3>
    <p role="status">{t("cockpit.openrouter." + cost.state)}</p>
    {(["estimated", "reserved", "reported"] as const).map(kind => <p key={kind}>{t("cockpit.openrouter." + kind, {
      amount: cost[kind + "_usd" as "estimated_usd" | "reserved_usd" | "reported_usd"] ?? t("cockpit.openrouter.unknown"),
    })}</p>)}
  </section>;
}
