"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  getQualityAnalysis,
  listQualityRecords,
  type QualityAnalysis,
  type QualityCampaignDraft,
  type QualityCounts,
  type QualityRecord,
} from "@/lib/academy-quality-api";
import { useTranslation } from "@/lib/i18n";

const SELECT = "h-9 w-full rounded-md border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-2 text-sm";
const QUALITY = "academy.campaigns.quality.";

function EvidenceCode({ code }: { readonly code: string }) {
  const t = useTranslation();
  const key = QUALITY + "issues." + code;
  const label = t(key);
  return label === key ? <code>{code}</code> : <>{label}</>;
}

function QualityComparison({ rows, reference }: { readonly rows: QualityCounts[]; readonly reference: boolean }) {
  const t = useTranslation();
  if (!rows.length) return <p className="text-sm text-hint">{t(QUALITY + "noCounts")}</p>;
  const value = (count?: number | null) => count ?? "—";
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="pb-2 text-left font-medium">{t(QUALITY + (reference ? "referenceComparison" : "baseComparison"))}</caption>
        <thead>
          <tr className="border-b border-[color:var(--ui-border)]">
            {["category", "sampleSize", reference ? "reference" : "base", "candidate", "lost", "gained"].map((column) => (
              <th key={column} scope="col" className="px-2 py-1">{t(QUALITY + column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.category} className="border-b border-[color:var(--ui-border)]">
              <th scope="row" className="px-2 py-1 font-normal">{row.category === "total" ? t(QUALITY + "total") : row.category}</th>
              <td className="px-2 py-1">{value(row.n)}</td>
              <td className="px-2 py-1">{value(reference ? row.reference_usable : row.base_usable)}</td>
              <td className="px-2 py-1">{value(row.candidate_usable)}</td>
              <td className="px-2 py-1">{value(row.lost_usable)}</td>
              <td className="px-2 py-1">{value(row.gained_usable)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.some((row) => row.lost_usable == null || row.gained_usable == null) && (
        <p className="mt-2 text-xs text-hint">{t(QUALITY + "missingPairCounts")}</p>
      )}
    </div>
  );
}

function QualityEvidence({ analysis }: { readonly analysis: QualityAnalysis }) {
  const t = useTranslation();
  const { record, comparison_issues: issues, findings, protected: protection } = analysis;
  const evidence = record.evidence_gaps ?? [];
  return (
    <details>
      <summary className="cursor-pointer text-sm font-medium">{t(QUALITY + "evidence")}</summary>
      <div className="mt-2 space-y-2 text-sm">
        <dl className="space-y-1">
          <div><dt className="text-hint">{t(QUALITY + "source")}</dt><dd className="break-all">{record.source.identity}</dd></div>
          {record.result_sha256 && (
            <div><dt className="text-hint">{t(QUALITY + "resultHash")}</dt><dd className="break-all"><code>{record.result_sha256}</code></dd></div>
          )}
          {protection && (
            <div>
              <dt className="text-hint">{t(QUALITY + "protectedCounts")}</dt>
              <dd>{protection.passed} / {protection.evaluated} / {protection.total}</dd>
            </div>
          )}
        </dl>
        {(issues.length > 0 || evidence.length > 0) && (
          <div>
            <p className="font-medium">{t(QUALITY + "knownGaps")}</p>
            <ul className="list-inside list-disc">
              {[...new Set([...issues, ...evidence])].map((code) => <li key={code}><EvidenceCode code={code} /></li>)}
            </ul>
          </div>
        )}
        {findings.length > 0 && (
          <ul className="space-y-1">
            {findings.map((finding, index) => (
              <li key={`${finding.code}-${index}`}>
                <EvidenceCode code={finding.code} />
                {finding.fields?.length ? <span> · {finding.fields.join(", ")}</span> : null}
                {finding.case_ids?.length ? <span className="break-all"> · {finding.case_ids.join(", ")}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}

function NextTrial({ analysis, disabled, onDraft }: {
  readonly analysis: QualityAnalysis;
  readonly disabled: boolean;
  readonly onDraft: (draft: QualityCampaignDraft) => void;
}) {
  const t = useTranslation();
  const { proposal } = analysis;
  const ready = proposal.status === "ready" && proposal.variants.length > 0;

  function prepare() {
    const reference = proposal.reference_id;
    onDraft({
      profileId: analysis.recommended_profile_id,
      variants: proposal.variants,
      fixed: proposal.fixed,
      qualityPolicy: {
        source_record_id: analysis.record.record_id,
        reference_record_ids: reference ? [reference] : [],
        protected_case_ids: analysis.protected_case_ids,
        protect_reference_hits: true,
        protect_base_hits: false,
        min_category_usable_delta: {},
        no_new_critical: true,
        hypothesis: t(QUALITY + "hypothesisText") + " " + proposal.factor + ".",
      },
    });
  }

  return (
    <section className="space-y-2 rounded-lg border border-[color:var(--ui-border)] p-3">
      <h4 className="font-medium">{t(QUALITY + "recommendation")}</h4>
      <p className="text-sm">{t(QUALITY + (ready ? "isolateFactor" : "noProposal"))}</p>
      {proposal.factor && <p className="text-sm text-hint">{t(QUALITY + "factor")} <code>{proposal.factor}</code></p>}
      {proposal.reasons.length > 0 && (
        <ul className="list-inside list-disc text-sm">
          {proposal.reasons.map((reason) => <li key={reason}><EvidenceCode code={reason} /></li>)}
        </ul>
      )}
      {ready && (
        <>
          <details className="text-sm">
            <summary className="cursor-pointer">{t(QUALITY + "variants")}</summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(proposal.variants, null, 2)}</pre>
            {proposal.fixed?.train_sha256 && <p className="mt-2 break-all">{t(QUALITY + "trainingHash")} <code>{proposal.fixed.train_sha256}</code></p>}
            {proposal.fixed?.runtime && (
              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(proposal.fixed.runtime, null, 2)}</pre>
            )}
          </details>
          {proposal.measurement?.length ? (
            <p className="text-sm">{t(QUALITY + "measurements")} · {proposal.measurement.map((item) => t(QUALITY + "measurement." + item)).join(", ")}</p>
          ) : null}
          {proposal.stop_condition && <p className="text-sm">{t(QUALITY + "stopCondition")}</p>}
          <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={prepare}>
            {t(QUALITY + "prepareDraft")}
          </Button>
        </>
      )}
    </section>
  );
}

export function CampaignQualityHistory({ disabled, onDraft }: {
  readonly disabled: boolean;
  readonly onDraft: (draft: QualityCampaignDraft) => void;
}) {
  const t = useTranslation();
  const [records, setRecords] = useState<QualityRecord[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [candidateId, setCandidateId] = useState("");
  const [referenceId, setReferenceId] = useState("");
  const [analysis, setAnalysis] = useState<QualityAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisFailed, setAnalysisFailed] = useState(false);
  const candidate = records?.find((record) => record.record_id === candidateId) ?? records?.[0];
  const reference = referenceId === candidate?.record_id ? "" : referenceId;

  useEffect(() => {
    const controller = new AbortController();
    void listQualityRecords(controller.signal)
      .then((items) => {
        if (controller.signal.aborted) return;
        setRecords(items);
        setLoadFailed(false);
      })
      .catch(() => { if (!controller.signal.aborted) setLoadFailed(true); });
    return () => controller.abort();
  }, [reload]);

  function clearAnalysis() {
    setAnalysis(null);
    setAnalysisFailed(false);
  }

  async function compare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!candidate || analyzing) return;
    clearAnalysis();
    setAnalyzing(true);
    try {
      setAnalysis(await getQualityAnalysis(candidate.record_id, reference));
    } catch {
      setAnalysisFailed(true);
    } finally {
      setAnalyzing(false);
    }
  }

  if (loadFailed) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <p role="alert" className="text-sm text-red-400">{t(QUALITY + "historyError")}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => setReload((value) => value + 1)}>
          {t("academy.common.retry")}
        </Button>
      </div>
    );
  }
  if (!records) return <p className="text-sm text-hint">{t(QUALITY + "loading")}</p>;
  if (!candidate) return <p className="text-sm text-hint">{t(QUALITY + "empty")}</p>;
  const alignedReference = Boolean(analysis?.reference_id && analysis.comparable);

  return (
    <div className="space-y-4">
      <form className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(event) => void compare(event)}>
        <div className="space-y-1">
          <Label htmlFor="quality-candidate">{t(QUALITY + "candidate")}</Label>
          <select id="quality-candidate" className={SELECT} value={candidate.record_id} disabled={analyzing}
            onChange={(event) => {
              setCandidateId(event.currentTarget.value);
              if (event.currentTarget.value === reference) setReferenceId("");
              clearAnalysis();
            }}>
            {records.map((item) => <option key={item.record_id} value={item.record_id}>{item.record_id} · {item.split}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="quality-reference">{t(QUALITY + "reference")}</Label>
          <select id="quality-reference" className={SELECT} value={reference} disabled={analyzing}
            onChange={(event) => { setReferenceId(event.currentTarget.value); clearAnalysis(); }}>
            <option value="">{t(QUALITY + "base")}</option>
            {records.filter((item) => item.record_id !== candidate.record_id).map((item) => (
              <option key={item.record_id} value={item.record_id}>{item.record_id} · {item.split}</option>
            ))}
          </select>
        </div>
        <Button type="submit" disabled={analyzing}>{t(QUALITY + "compare")}</Button>
      </form>
      {analysisFailed && <p role="alert" className="text-sm text-red-400">{t(QUALITY + "analysisError")}</p>}
      {analysis && (
        <div className="space-y-4">
          <dl className="text-sm">
            <dt className="text-hint">{t(QUALITY + "decision")}</dt>
            <dd className="font-semibold">{analysis.decision} · {t(QUALITY + "outcome." + analysis.decision)}</dd>
          </dl>
          {analysis.reference_id && !analysis.comparable && (
            <output className="block text-sm text-hint">{t(QUALITY + "notComparable")}</output>
          )}
          <QualityComparison rows={alignedReference ? analysis.comparison : analysis.summary} reference={alignedReference} />
          <QualityEvidence analysis={analysis} />
          <NextTrial analysis={analysis} disabled={disabled} onDraft={onDraft} />
        </div>
      )}
    </div>
  );
}
