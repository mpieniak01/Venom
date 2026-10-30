import type { VastEnvironment } from "./hooks/use-vast-environments";

const knownStates = new Set(["planned", "creating", "running", "stopped", "destroyed", "failed", "unknown"]);

export function VastEnvironmentHistory({ rows, t }: Readonly<{
  rows: VastEnvironment[];
  t: (key: string) => string;
}>) {
  const text = (name: string) => t("models.vast." + name);
  return <section className="space-y-3" aria-label={text("history")}>
    <h3 className="font-semibold">{text("history")}</h3>
    <p className="text-xs text-[color:var(--ui-muted)]">{text("historyHint")}</p>
    {rows.length === 0 ? <p className="text-sm">{text("noHistory")}</p> :
      <div className="overflow-auto"><table className="w-full text-left text-sm">
        <caption className="sr-only">{text("history")}</caption>
        <thead><tr>{["plan", "historyModel", "instance", "recordedState", "unavailableReason"].map(key =>
          <th key={key} scope="col" className="p-2">{text(key)}</th>
        )}</tr></thead>
        <tbody>{rows.map(row => <tr key={row.plan_id} className="border-t border-[color:var(--ui-border)]">
          <td className="p-2 font-mono text-xs">{row.plan_id}</td>
          <td className="p-2 break-all">{row.model || text("unknown")}</td>
          <td className="p-2">{row.instance_id ?? text("unknown")}</td>
          <td className="p-2">{text("historyStates." + (knownStates.has(row.state) ? row.state : "unknown"))}</td>
          <td className="p-2"><code>{row.error ?? "—"}</code></td>
        </tr>)}</tbody>
      </table></div>}
  </section>;
}
