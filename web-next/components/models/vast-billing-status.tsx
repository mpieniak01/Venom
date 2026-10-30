import { Badge } from "@/components/ui/badge";
import { formatVastUsd } from "@/lib/vast-price";
import type { VastEnvironment } from "./hooks/use-vast-environments";

export function VastBillingStatus({ row, t }: Readonly<{
  row: VastEnvironment; t: (key: string) => string;
}>) {
  const unknown = t("models.vast.unknown");
  const amount = formatVastUsd(row.billed_usd, unknown);
  let status = row.billing_status ?? "unverified";
  if (status === "reported" && amount === unknown) status = "unverified";
  const reported = status === "reported";
  return <span className="inline-flex flex-wrap items-center gap-2">
    <Badge tone={reported || status === "not_applicable" ? "neutral" : "warning"}>{t("models.vast.billingStates." + status)}</Badge>
    {reported && <span className="font-mono text-xs">{amount} USD</span>}
  </span>;
}
