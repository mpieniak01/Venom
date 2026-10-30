import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/date";
import { formatVastUsd } from "@/lib/vast-price";
import type { VastAccountBilling } from "./hooks/use-vast-environments";
import { remoteModelStyles as styles } from "./remote-model-styles";

export function VastAccountBillingPanel({ billing, pending, enabled, sync, t }: Readonly<{
  billing: VastAccountBilling; pending: boolean; enabled: boolean;
  sync: (reconcile?: boolean) => Promise<void>; t: (key: string) => string;
}>) {
  const text = (name: string) => t("models.vast.accountBilling." + name);
  const unknown = t("models.vast.unknown");
  const metrics = [
    ["credit", billing.credit_usd],
    [billing.complete ? "spent" : "partialSpent", billing.total_usd],
    ["managed", billing.managed_usd],
    ["other", billing.other_usd],
  ] as const;
  return <section className={styles.panel + " space-y-4"} aria-label={text("title")}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className={styles.heading}>{text("title")}</h2>
      <Badge tone={billing.status === "ready" && !billing.account_error ? "neutral" : "warning"}>
        {text("states." + (billing.account_error ? "stale" : billing.status))}
      </Badge>
    </div>
    <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map(([name, value]) => <div key={name} className={styles.card}>
        <dt className={styles.hint}>{text(name)}</dt>
        <dd className="mt-2 font-mono text-base text-[color:var(--text-primary)]">{formatVastUsd(value ?? null, unknown)}{value != null && " USD"}</dd>
      </div>)}
    </dl>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className={styles.hint}>
        <p>{text("period")}: {billing.from_utc} — {billing.to_utc} UTC</p>
        <p>{text("updated")}: {billing.account_observed_at ? formatDateTime(billing.account_observed_at) : unknown}</p>
        {billing.covered_days < billing.expected_days && <p>{text("progress")}: {billing.covered_days} / {billing.expected_days}</p>}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" disabled={pending || !enabled || !billing.configured} onClick={() => void sync()}>{text(pending ? "working" : "refresh")}</Button>
        <Button size="sm" variant="ghost" disabled={pending || !enabled || !billing.configured} onClick={() => void sync(true)}>{text("reconcile")}</Button>
      </div>
    </div>
  </section>;
}
