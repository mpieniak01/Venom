import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { OpenRouterModel } from "./hooks/use-openrouter-models";
import { remoteModelStyles as styles } from "./remote-model-styles";

interface Props {
  models: OpenRouterModel[];
  connected: OpenRouterModel[];
  pending: Record<string, boolean>;
  manage: (id: string, connect: boolean) => Promise<unknown>;
  caption: string;
  t: (key: string) => string;
}
function price(value: string | null, unknown: string): string {
  const raw = value?.trim();
  if (!raw || !Number.isFinite(Number(raw)) || Number(raw) < 0) return unknown;
  if (Number(raw) === 0) return "0";
  const dot = raw.indexOf(".");
  if (dot < 0 || raw.toLowerCase().includes("e")) return raw;
  let end = raw.length;
  while (end > dot && raw[end - 1] === "0") end--;
  if (end === dot + 1) end = dot;
  return raw.slice(0, end);
}

export function OpenRouterModelTable({ models, connected, pending, manage, caption, t }: Readonly<Props>) {
  const text = (key: string) => t("models.openrouter." + key);
  const connections = new Map(connected.map(model => [model.id, model]));
  return <div className={styles.tableWrap + " max-h-[640px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--primary)]"} role="region" aria-label={caption} tabIndex={0}>
    <table className="w-full min-w-[960px] border-collapse text-left text-sm">
      <caption className="sr-only">{caption}</caption>
      <thead className="sticky top-0 z-10 bg-[color:var(--ui-surface)]"><tr>
        {["model", "context", "input", "output", "tools", "status", "actions"].map(key => <th key={key} scope="col" className={styles.tableHead}><span className={["context", "input", "output"].includes(key) ? "block text-right" : undefined}>{text("table." + key)}</span></th>)}
      </tr></thead>
      <tbody>{models.map(model => {
        const inputPrice = price(model.input_price_per_million, text("unknown"));
        const outputPrice = price(model.output_price_per_million, text("unknown"));
        const connection = connections.get(model.id);
        const isConnected = Boolean(connection);
        const stale = connection?.available === false;
        const cap = connection?.max_output_tokens;
        const busy = Boolean(pending[model.id]);
        const statusKey = isConnected ? "connected" : "table.notConnected";
        const statusTone = isConnected ? "success" : "neutral";
        let action = isConnected ? "disconnect" : "connect";
        if (busy) action = "saving";
        return <tr key={model.id} className={styles.tableRow}>
          <th scope="row" className={styles.tableCell + " min-w-[240px] max-w-[320px] align-top text-left font-normal"}>
            <p className="break-words text-sm font-semibold">{model.name}</p>
            <p className="mt-1 break-all font-mono text-[11px] text-[color:var(--ui-muted)]">{model.id}</p>
            {(model.description || cap !== undefined) && <details className="mt-2 text-xs text-[color:var(--ui-muted)]">
              <summary className="w-fit cursor-pointer rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--primary)]" aria-label={`${text("table.details")}: ${model.id}`}>{text("table.details")}</summary>
              <div className="mt-2 space-y-2 leading-relaxed">
                {cap !== undefined && <p>{text("outputLimit")}: <span className="font-mono">{cap.toLocaleString()}</span></p>}
                {model.description && <p className="whitespace-pre-line break-words">{model.description}</p>}
              </div>
            </details>}
          </th>
          <td className={styles.tableCell + " whitespace-nowrap text-right align-top font-mono tabular-nums"}>{model.context_length?.toLocaleString() ?? text("unknown")}</td>
          <td className={styles.tableCell + " whitespace-nowrap text-right align-top font-mono tabular-nums" + (inputPrice === "0" ? " text-emerald-400" : "")}>{inputPrice}</td>
          <td className={styles.tableCell + " whitespace-nowrap text-right align-top font-mono tabular-nums" + (outputPrice === "0" ? " text-emerald-400" : "")}>{outputPrice}</td>
          <td className={styles.tableCell + " align-top"}><Badge tone="neutral">{text("table." + (model.supports_tools ? "yes" : "no"))}</Badge></td>
          <td className={styles.tableCell + " align-top"}><Badge tone={stale ? "warning" : statusTone}>{text(stale ? "needsRefresh" : statusKey)}</Badge></td>
          <td className={styles.tableCell + " min-w-[160px] align-top"}><div className="flex flex-col items-start gap-2">
            {stale && <Button size="sm" variant="secondary" disabled={busy} aria-label={`${text("refresh")}: ${model.id}`} onClick={() => void manage(model.id, true)}>{text("refresh")}</Button>}
            <Button size="sm" variant="secondary" disabled={busy} aria-label={`${text(isConnected ? "disconnect" : "connect")}: ${model.id}`} onClick={() => void manage(model.id, !isConnected)}>{text(action)}</Button>
          </div></td>
        </tr>;
      })}</tbody>
    </table>
  </div>;
}
