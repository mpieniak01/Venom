import type { VastEnvironment } from "./hooks/use-vast-environments";
import { remoteModelStyles as styles } from "./remote-model-styles";

const knownStates = new Set(["planned", "creating", "running", "stopped", "destroyed", "failed", "unknown"]);

export function VastEnvironmentHistory({ rows, t }: Readonly<{
  rows: VastEnvironment[];
  t: (key: string) => string;
}>) {
  const text = (name: string) => t("models.vast." + name);
  return <section className={styles.panel + " space-y-4"} aria-label={text("history")}>
    <h3 className={styles.heading}>{text("history")}</h3>
    <p className={styles.hint}>{text("historyHint")}</p>
    {rows.length === 0 ? <p className="text-sm">{text("noHistory")}</p> :
      <div className={styles.tableWrap}><table className="w-full min-w-[720px] border-collapse whitespace-nowrap text-left text-sm">
        <caption className="sr-only">{text("history")}</caption>
        <thead><tr>{["plan", "historyModel", "instance", "recordedState", "unavailableReason"].map(key =>
          <th key={key} scope="col" className={styles.tableHead}>{text(key)}</th>
        )}</tr></thead>
        <tbody>{rows.map(row => <tr key={row.plan_id} className={styles.tableRow}>
          <td className={styles.tableCell + " font-mono text-[11px]"}>{row.plan_id}</td>
          <td className={styles.tableCell}>{row.model || text("unknown")}</td>
          <td className={styles.tableCell}>{row.instance_id ?? text("unknown")}</td>
          <td className={styles.tableCell}>{text("historyStates." + (knownStates.has(row.state) ? row.state : "unknown"))}</td>
          <td className={styles.tableCell}><code>{row.error ?? "—"}</code></td>
        </tr>)}</tbody>
      </table></div>}
  </section>;
}
