"use client";

import {
  DATA_AUDIT,
  dataAuditErrorKey,
  type DataAudit,
  type DataAuditGroup,
  type PassedDataAudit,
} from "@/lib/academy-data-audit";
import { useLanguage, useTranslation } from "@/lib/i18n";

const GROUPS: DataAuditGroup[] = ["replay", "fresh"];

function AuditGroups({ report }: { readonly report: PassedDataAudit["report"] }) {
  const { t, language } = useLanguage();
  const number = new Intl.NumberFormat(language);
  const percent = new Intl.NumberFormat(language, { style: "percent", maximumFractionDigits: 1 });
  function share(count: number, total: number) {
    const counts = `${number.format(count)} / ${number.format(total)}`;
    return total ? `${counts} (${percent.format(count / total)})` : counts;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{t(DATA_AUDIT + "groups")}</caption>
        <thead>
          <tr className="border-b border-[color:var(--ui-border)]">
            <th scope="col" className="p-1">{t(DATA_AUDIT + "group")}</th>
            <th scope="col" className="p-1">{t(DATA_AUDIT + "metrics.records")}</th>
            <th scope="col" className="p-1">{t(DATA_AUDIT + "metrics.supervised_tokens")}</th>
          </tr>
        </thead>
        <tbody>
          {GROUPS.map((key) => (
            <tr key={key}>
              <th scope="row" className="p-1 font-normal">{t(DATA_AUDIT + key)}</th>
              <td className="whitespace-nowrap p-1">{share(report.groups[key].records, report.totals.records)}</td>
              <td className="whitespace-nowrap p-1">{share(report.groups[key].supervised_tokens, report.totals.supervised_tokens)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditCoverage({ report }: { readonly report: PassedDataAudit["report"] }) {
  const { t, language } = useLanguage();
  const number = new Intl.NumberFormat(language);
  const skills = Object.entries(report.skills).sort(([left], [right]) => left.localeCompare(right, language));

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="pb-1 text-left font-medium">{t(DATA_AUDIT + "skills")}</caption>
        <thead>
          <tr className="border-b border-[color:var(--ui-border)]">
            <th scope="col" className="p-1">{t(DATA_AUDIT + "skill")}</th>
            {GROUPS.map((group) => <th key={group} scope="col" className="p-1">{t(DATA_AUDIT + group)}</th>)}
          </tr>
        </thead>
        <tbody>
          {skills.map(([skill, groups]) => (
            <tr key={skill} className="border-b border-[color:var(--ui-border)]">
              <th scope="row" className="break-words p-1 font-normal">{skill}</th>
              {GROUPS.map((group) => (
                <td key={group} className="whitespace-nowrap p-1">
                  {number.format(groups[group].records)} / {number.format(groups[group].supervised_tokens)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="my-1 text-xs text-hint">{t(DATA_AUDIT + "skillHint")}</p>
    </div>
  );
}

function AuditEvidence({ report, hash }: {
  readonly report: PassedDataAudit["report"];
  readonly hash?: string;
}) {
  const { t, language } = useLanguage();
  const number = new Intl.NumberFormat(language);
  return (
    <div className="space-y-3">
      <dl className="flex flex-wrap gap-3 text-sm">
        <div><dt className="text-hint">{t(DATA_AUDIT + "tokenLimit")}</dt><dd>{number.format(report.tokenization.max_tokens)}</dd></div>
        <div><dt className="text-hint">{t(DATA_AUDIT + "maxLength")}</dt><dd>{number.format(report.totals.max_input_tokens)}</dd></div>
        <div><dt className="text-hint">{t(DATA_AUDIT + "maxSupervised")}</dt><dd>{number.format(report.totals.max_supervised_tokens)}</dd></div>
        <div><dt className="text-hint">{t(DATA_AUDIT + "sharedPrefixes")}</dt><dd>{number.format(report.leakage.supervised_prefix_matches)}</dd></div>
        <div><dt className="text-hint">{t(DATA_AUDIT + "sharedQuestions")}</dt><dd>{number.format(report.leakage.final_user_matches)}</dd></div>
        <div><dt className="text-hint">{t(DATA_AUDIT + "duplicates")}</dt><dd>{number.format(report.leakage.duplicate_train_records)}</dd></div>
      </dl>
      <p className="text-xs text-hint">{t(DATA_AUDIT + "compositionHint")}</p>
      {hash && <p className="break-all text-xs text-hint">{t(DATA_AUDIT + "reportHash")} <code>{hash}</code></p>}
    </div>
  );
}

function BlockedAuditNotice({ audit }: { readonly audit: Extract<DataAudit, { status: "blocked" }> }) {
  const { t, language } = useLanguage();
  const key = dataAuditErrorKey(audit.error);
  const message = key ? t(key) : null;
  const number = new Intl.NumberFormat(language);

  return (
    <div role="alert" className="space-y-1 text-sm text-red-400">
      <p className="font-medium">{t(DATA_AUDIT + "blocked")}</p>
      {message && message !== key && <p>{message}</p>}
      {audit.violations?.length ? (
        <ul className="list-inside list-disc">
          {audit.violations.map(({ group, skill, metric, actual, minimum }) => (
            <li key={`${group}-${skill ?? ""}-${metric}`}>
              {t(DATA_AUDIT + group)}{skill ? ` · ${skill}` : ""} · {t(DATA_AUDIT + "metrics." + metric)}
              {" · "}{number.format(actual)} / {t(DATA_AUDIT + "minimum")} {number.format(minimum)}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function DataAuditSummary({ audit }: { readonly audit?: DataAudit | null }) {
  const t = useTranslation();
  if (!audit) return <p className="text-sm text-hint">{t(DATA_AUDIT + "unaudited")}</p>;

  const report = audit.report;
  return (
    <div className="space-y-2">
      {audit.status === "blocked" && <BlockedAuditNotice audit={audit} />}
      {report && (
        <details className="space-y-3 rounded-lg border border-[color:var(--ui-border)] p-3">
          <summary className="cursor-pointer text-sm font-semibold">
            {t(DATA_AUDIT + (audit.status === "passed" ? "passed" : "report"))}
          </summary>
          <div className="space-y-3 pt-2">
            <AuditGroups report={report} />
            <AuditCoverage report={report} />
            <AuditEvidence report={report} hash={audit.report_sha256} />
          </div>
        </details>
      )}
    </div>
  );
}
