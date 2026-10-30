import type { OpenRouterCost as Cost } from "@/lib/openrouter-chat";

/** Show unknown/pending accounting explicitly even when an interrupted turn has no usage. */
export function OpenRouterCost({cost, t}: Readonly<{
  cost: Cost; t: (key: string, values?: Record<string, string | number>) => string;
}>) {
  return <section data-testid="openrouter-cost" className="space-y-1 text-sm">
    <h3>{t("cockpit.openrouter.costTitle")}</h3>
    <output className="block" aria-live="polite">{t("cockpit.openrouter." + cost.state)}</output>
    {(["estimated", "reserved", "reported"] as const).map(kind => <p key={kind}>{t("cockpit.openrouter." + kind, {
      amount: cost[kind + "_usd" as "estimated_usd" | "reserved_usd" | "reported_usd"] ?? t("cockpit.openrouter.unknown"),
    })}</p>)}
    <h4>{t("cockpit.openrouter.conversationTitle")}</h4>
    <p>{t("cockpit.openrouter." + cost.conversation_state)}</p>
    <p>{t("cockpit.openrouter.conversationReported", {amount: cost.conversation_reported_usd ?? t("cockpit.openrouter.unknown")})}</p>
    <p>{t("cockpit.openrouter.conversationReserved", {amount: cost.conversation_reserved_usd ?? t("cockpit.openrouter.unknown")})}</p>
  </section>;
}
