import { useState } from "react";
import { formatVastUsd } from "@/lib/vast-price";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { VastEnvironment } from "./hooks/use-vast-environments";
import { remoteModelStyles as styles } from "./remote-model-styles";

interface Props {
  row: VastEnvironment; pending: boolean; t: (key: string) => string;
  action: (planId: string, operation: "refresh" | "stop" | "destroy") => Promise<void>;
}
const knownPhases = new Set(["planned", "queued", "creating", "waiting", "provisioning", "connecting", "ready", "error", "interrupted", "stopped", "destroyed", "stop_requested", "destroy_requested", "cancelled"]);
export function VastEnvironmentRow({ row, pending, action, t }: Readonly<Props>) {
  const [confirm, setConfirm] = useState<"stop" | "destroy" | null>(null);
  const text = (name: string) => t("models.vast." + name);
  const phase = knownPhases.has(row.phase) ? row.phase : "unknown";
  const cancellable = row.phase === "interrupted" && row.instance_id === null && !row.billing_possible;
  const canManage = (row.instance_id !== null || cancellable) && !["destroyed", "cancelled"].includes(row.phase);
  const awaitingCleanup = ["stop_requested", "destroy_requested"].includes(row.phase);
  const provisioning = ["queued", "creating", "waiting", "provisioning", "connecting"].includes(row.phase);
  return <li className={styles.card + " space-y-4"}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="min-w-0"><p className="break-all text-sm font-semibold text-[color:var(--text-primary)]">{row.model}</p><p className="text-xs text-[color:var(--ui-muted)] break-all">{row.plan_id}</p></div>
      <div className="flex flex-wrap gap-2"><Badge tone={row.phase === "error" || row.phase === "interrupted" ? "danger" : "neutral"}>{text("phases." + phase)}</Badge>{row.connected && <Badge tone="success">{text("connected")}</Badge>}</div>
    </div>
    <div className="grid gap-3 text-xs text-[color:var(--ui-muted)] sm:grid-cols-3"><span>{text("instance")}: {row.instance_id ?? text("unknown")}</span><span>{text("hourly")}: {formatVastUsd(row.hourly_usd, text("unknown"))}</span><span>{text("estimate")}: {formatVastUsd(row.total_usd, text("unknown"))}</span></div>
    {row.billing_possible && <p className="text-xs text-amber-300">{text("billingWarning")}</p>}
    {row.connected && <p className="text-sm">{text("chatReady")}</p>}
    {row.error && <p role="alert" className="text-xs text-rose-400">{text("operationError")}: <code>{row.error}</code></p>}
    <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="secondary" disabled={pending || provisioning || row.phase === "destroyed" || row.phase === "planned"} onClick={() => void action(row.plan_id, "refresh")}>{text("refresh")}</Button>
      <Button size="sm" variant="secondary" disabled={pending || provisioning || awaitingCleanup || !canManage || cancellable || row.phase === "stopped"} onClick={() => setConfirm("stop")}>{text("stop")}</Button>
      <Button size="sm" variant="secondary" disabled={pending || provisioning || awaitingCleanup || !canManage} onClick={() => setConfirm("destroy")}>{text("destroy")}</Button>
    </div>
    {confirm && canManage && !provisioning && !awaitingCleanup && <fieldset aria-label={text("confirmAction")} className="rounded-xl border border-amber-500/40 p-3 space-y-2">
      <p className="text-sm">{text(confirm === "stop" ? "stopHint" : "destroyHint")}</p>
      <div className="flex flex-wrap gap-2"><Button size="sm" disabled={pending} onClick={() => { const operation = confirm; setConfirm(null); void action(row.plan_id, operation); }}>{text(confirm === "stop" ? "confirmStop" : "confirmDestroy")}</Button><Button size="sm" variant="secondary" onClick={() => setConfirm(null)}>{text("cancel")}</Button></div>
    </fieldset>}
  </li>;
}
