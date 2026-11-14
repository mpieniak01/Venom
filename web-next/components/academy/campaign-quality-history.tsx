"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  getQualityAnalysis,
  listQualityRecords,
  type QualityAnalysis,
  type QualityCampaignDraft,
  type QualityCounts,
  type QualityListing,
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
  const formatCritical = (count: number | null | undefined, n: number) =>
    count == null ? "—" : `${count} / ${n}`;
  const peerCritical = (row: QualityCounts) => reference ? row.reference_critical : row.base_critical;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="pb-2 text-left font-medium">{t(QUALITY + (reference ? "referenceComparison" : "baseComparison"))}</caption>
        <thead>
          <tr className="border-b border-[color:var(--ui-border)]">
            {["category", "sampleSize", reference ? "reference" : "base", "candidate", "lost", "gained"].map((column) => (
              <th key={column} scope="col" className="px-2 py-1">{t(QUALITY + column)}</th>
            ))}
            <th scope="col" className="px-2 py-1">{t(QUALITY + "criticalComparison")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const categoryKey = QUALITY + "categories." + row.category;
            const category = row.category === "total" ? t(QUALITY + "total") : t(categoryKey);
            return (
              <tr key={row.category} className="border-b border-[color:var(--ui-border)]">
                <th scope="row" className="px-2 py-1 font-normal">{category === categoryKey ? row.category : category}</th>
                <td className="px-2 py-1">{value(row.n)}</td>
                <td className="px-2 py-1">{value(reference ? row.reference_usable : row.base_usable)}</td>
                <td className="px-2 py-1">{value(row.candidate_usable)}</td>
                <td className="px-2 py-1">{value(row.lost_usable)}</td>
                <td className="px-2 py-1">{value(row.gained_usable)}</td>
                <td className="whitespace-nowrap px-2 py-1">
                  {formatCritical(peerCritical(row), row.n)} → {formatCritical(row.candidate_critical, row.n)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-hint">{t(QUALITY + "criticalComparisonHint")}</p>
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
      ...(proposal.fixed ? { fixed: proposal.fixed } : {}),
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

export function CampaignQualityHistory({ disabled, initialRecordId = "", refresh = 0, onDraft }: {
  readonly disabled: boolean;
  readonly initialRecordId?: string;
  readonly refresh?: number;
  readonly onDraft: (draft: QualityCampaignDraft) => void;
}) {
  const t = useTranslation();
  const [listing, setListing] = useState<QualityListing | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [candidateId, setCandidateId] = useState(initialRecordId);
  const [referenceId, setReferenceId] = useState("");
  const [retry, setRetry] = useState(0);
  const [response, setResponse] = useState<{
    recordId: string; reference: string; retry: number; refresh: number; result: QualityAnalysis | null;
  } | null>(null);
  const records = listing?.records;
  const candidate = candidateId
    ? records?.find((record) => record.record_id === candidateId)
    : records?.find((record) => record.split === "dev" && record.outcome) ?? records?.[0];
  const recordId = candidate?.record_id;
  const reference = referenceId === recordId ? "" : referenceId;
  const current = response?.recordId === recordId && response?.reference === reference && response?.retry === retry && response.refresh === refresh
    ? response : null;
  const analysis = current?.result;

  useEffect(() => {
    const controller = new AbortController();
    void listQualityRecords(controller.signal)
      .then((nextListing) => {
        if (controller.signal.aborted) return;
        setListing(nextListing);
        setLoadFailed(false);
      })
      .catch(() => { if (!controller.signal.aborted) setLoadFailed(true); });
    return () => controller.abort();
  }, [reload, refresh]);

  useEffect(() => {
    if (!recordId) return;
    const controller = new AbortController();
    function publish(result: QualityAnalysis | null) {
      if (!controller.signal.aborted && recordId) setResponse({ recordId, reference, retry, refresh, result });
    }
    void getQualityAnalysis(recordId, reference, controller.signal)
      .then(publish)
      .catch(() => publish(null));
    return () => controller.abort();
  }, [recordId, reference, retry, refresh]);

  function selectCandidate(id: string) {
    if (id === recordId) return;
    setResponse(null);
    setCandidateId(id);
    if (id === reference) setReferenceId("");
  }

  function selectReference(id: string) {
    if (id === reference) return;
    setResponse(null);
    setReferenceId(id);
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
  const unavailableIds = listing?.unavailable_record_ids ?? [];
  const unavailableFeedback = unavailableIds.length > 0 ? (
    <output className="block break-all text-sm text-hint">
      {t(QUALITY + "unavailableRecords")} <code>{unavailableIds.join(", ")}</code>
    </output>
  ) : null;
  if (!candidate && !candidateId) return unavailableFeedback ?? <p className="text-sm text-hint">{t(QUALITY + "empty")}</p>;

  return (
    <div className="space-y-4">
      {unavailableFeedback}
      {!candidate && candidateId && <output className="block text-sm text-hint">{t(QUALITY + "selectedUnavailable")}</output>}
      <div className="grid items-end gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="quality-candidate">{t(QUALITY + "candidate")}</Label>
          <select id="quality-candidate" className={SELECT} value={recordId ?? ""} onChange={(event) => selectCandidate(event.currentTarget.value)}>
            {!candidate && <option value="" disabled>{t(QUALITY + "selectRecord")}</option>}
            {records.map((item) => <option key={item.record_id} value={item.record_id}>{item.record_id} · {item.split}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="quality-reference">{t(QUALITY + "reference")}</Label>
          <select id="quality-reference" className={SELECT} value={reference} onChange={(event) => selectReference(event.currentTarget.value)}>
            <option value="">{t(QUALITY + "base")}</option>
            {records.filter((item) => item.record_id !== candidate?.record_id).map((item) => (
              <option key={item.record_id} value={item.record_id}>{item.record_id} · {item.split}</option>
            ))}
          </select>
        </div>
      </div>
      {recordId && !current && <p role="status" className="text-sm text-hint">{t(QUALITY + "loadingAnalysis")}</p>}
      {current && !analysis && (
        <div className="flex flex-wrap items-center gap-2">
          <p role="alert" className="text-sm text-red-400">{t(QUALITY + "analysisError")}</p>
          <Button type="button" size="sm" variant="outline" onClick={() => setRetry((value) => value + 1)}>
            {t("academy.common.retry")}
          </Button>
        </div>
      )}
      {analysis && <QualityAnalysisResult analysis={analysis} disabled={disabled} onDraft={onDraft} />}
    </div>
  );
}

function QualityAnalysisResult({ analysis, disabled, onDraft }: {
  readonly analysis: QualityAnalysis;
  readonly disabled: boolean;
  readonly onDraft: (draft: QualityCampaignDraft) => void;
}) {
  const t = useTranslation();
  const alignedReference = Boolean(analysis.reference_id && analysis.comparable);
  const cohorts = alignedReference ? analysis.cohort_comparison : analysis.cohorts;
  const categories = alignedReference ? analysis.comparison : analysis.summary;

  return (
    <div className="space-y-4">
      <dl className="text-sm">
        <dt className="text-hint">{t(QUALITY + "decision")}</dt>
        <dd className="font-semibold">{analysis.decision} · {t(QUALITY + "outcome." + analysis.decision)}</dd>
      </dl>
      {analysis.reference_id && !analysis.comparable && (
        <output className="block text-sm text-hint">{t(QUALITY + "notComparable")}</output>
      )}
      {cohorts?.length ? (
        <>
          <QualityComparison rows={cohorts} reference={alignedReference} />
          {categories.length ? (
            <details>
              <summary className="cursor-pointer text-sm">{t(QUALITY + "categoryBreakdown")}</summary>
              <QualityComparison rows={categories} reference={alignedReference} />
            </details>
          ) : null}
        </>
      ) : <QualityComparison rows={categories} reference={alignedReference} />}
      <QualityEvidence analysis={analysis} />
      <NextTrial analysis={analysis} disabled={disabled} onDraft={onDraft} />
    </div>
  );
}
