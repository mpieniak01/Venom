"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  getExperimentReport,
  getExperimentReview,
  type ExperimentAnswer,
  type ExperimentMessage,
  type ExperimentReport,
  type ExperimentReview,
  type ExperimentRun,
  type ExperimentVerdict,
} from "@/lib/academy-experiments-api";
import { useLanguage, useTranslation } from "@/lib/i18n";
import { DataAuditSummary } from "./data-audit-summary";
import { InitialAdapterSummary } from "./initial-adapter";

const METRICS = [
  ["semantic", "academy.experiments.semantic"],
  ["usable", "academy.experiments.usable"],
  ["passed", "academy.experiments.passed"],
  ["format", "academy.experiments.format"],
  ["critical", "academy.experiments.critical"],
  ["runtime_or_length_failure", "academy.experiments.runtimeFailure"],
] as const;

function downloadJson(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

function Conversation({ messages }: { readonly messages?: ExperimentMessage[] }) {
  if (!messages?.length) return null;
  return (
    <dl className="space-y-2 border-b border-[color:var(--ui-border)] pb-3 text-sm">
      {messages.map((message, index) => (
        <div key={`${message.role}-${index}`}>
          <dt className="font-medium">{message.role}</dt>
          <dd className="whitespace-pre-wrap break-words">{message.content}</dd>
        </div>
      ))}
    </dl>
  );
}

interface AnswerProps {
  readonly title: string;
  readonly answer?: ExperimentAnswer;
  readonly verdict?: ExperimentVerdict;
}

function Answer({ title, answer, verdict }: AnswerProps) {
  const t = useTranslation();
  return (
    <div className="min-w-0 space-y-2 rounded-lg border border-[color:var(--ui-border)] p-3">
      <p className="text-sm font-medium">{title}</p>
      <p className="whitespace-pre-wrap break-words text-sm">{answer?.text || t("academy.experiments.noAnswer")}</p>
      {verdict && (
        <dl className="flex flex-wrap gap-3 text-xs text-hint">
          {METRICS.slice(0, 3).map(([metric, label]) => (
            <div key={metric}>
              <dt>{t(label)}</dt>
              <dd>{t(verdict[metric as keyof ExperimentVerdict] ? "academy.experiments.yes" : "academy.experiments.no")}</dd>
            </div>
          ))}
        </dl>
      )}
      {answer?.reason && <p className="break-words text-sm text-hint">{answer.reason}</p>}
      {answer?.error && <p className="break-words text-sm text-red-400">{answer.error}</p>}
      {answer?.finish && answer.finish !== "stop" && <p className="text-sm text-hint">{answer.finish}</p>}
    </div>
  );
}

function Comparison({ report, task }: { readonly report: ExperimentReport; readonly task: string }) {
  const { t, language } = useLanguage();
  const base = report.summaries.base[task];
  const candidate = report.summaries.candidate[task];
  if (!base || !candidate) return null;
  const formatter = new Intl.NumberFormat(language, { signDisplay: "exceptZero", maximumFractionDigits: 1 });

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm" aria-label={t("academy.experiments.comparison")}>
        <thead>
          <tr className="border-b border-[color:var(--ui-border)]">
            <th scope="col" className="py-2 pr-3">{t("academy.experiments.metric")}</th>
            <th scope="col" className="px-3 py-2">{t("academy.experiments.base")}</th>
            <th scope="col" className="px-3 py-2">{t("academy.experiments.candidate")}</th>
            <th scope="col" className="px-3 py-2">{t("academy.experiments.delta")}</th>
          </tr>
        </thead>
        <tbody>
          {METRICS.map(([metric, label]) => (
            <tr key={metric} className="border-b border-[color:var(--ui-border)]">
              <th scope="row" className="py-2 pr-3 font-normal">{t(label)}</th>
              <td className="px-3 py-2">{base[metric]} / {base.n}</td>
              <td className="px-3 py-2">{candidate[metric]} / {candidate.n}</td>
              <td className="px-3 py-2">{base.n && candidate.n
                ? formatter.format(100 * (candidate[metric] / candidate.n - base[metric] / base.n))
                : t("academy.experiments.unavailable")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ExperimentResult({ run, onOpenQuality }: {
  readonly run: ExperimentRun;
  readonly onOpenQuality?: (recordId: string) => void;
}) {
  const { t, language } = useLanguage();
  const [report, setReport] = useState<ExperimentReport | null>(run.report ?? null);
  const [failed, setFailed] = useState(false);
  const [request, setRequest] = useState(0);
  const [task, setTask] = useState("total");

  useEffect(() => {
    const abort = new AbortController();
    void getExperimentReport(run.run_id, abort.signal)
      .then((result) => { if (!abort.signal.aborted) setReport(result); })
      .catch(() => { if (!abort.signal.aborted) setFailed(true); });
    return () => abort.abort();
  }, [run.run_id, run.updated_at, request]);

  if (!report) {
    if (!failed) return <p className="text-sm text-hint">{t("academy.experiments.loadingReport")}</p>;
    return (
      <div className="flex flex-wrap items-center gap-2">
        <p role="alert" className="text-sm text-red-400">{t("academy.experiments.reportError")}</p>
        <Button type="button" size="sm" variant="outline" onClick={() => { setFailed(false); setRequest((value) => value + 1); }}>
          {t("academy.common.retry")}
        </Button>
      </div>
    );
  }

  const tasks = Object.keys(report.summaries.base)
    .filter((key) => key !== "total" && Object.hasOwn(report.summaries.candidate, key))
    .sort((left, right) => left.localeCompare(right, language));
  const selectedTask = tasks.includes(task) ? task : "total";
  const audit = report.data_audit ?? run.data_audit;
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-semibold">{t("academy.experiments.comparison")}</h4>
        <div className="flex flex-wrap gap-2">
          {onOpenQuality && run.attempt > 0 && !report.historical && (
            <Button type="button" variant="outline" size="sm" onClick={() => onOpenQuality(run.run_id)}>
              {t("academy.experiments.openQuality")}
            </Button>
          )}
          <Button type="button" variant="outline" size="sm"
            onClick={() => downloadJson(`experiment-${run.run_id}.json`, report)}>
            {t("academy.experiments.downloadReport")}
          </Button>
        </div>
      </div>
      {run.attempt > 0 && <InitialAdapterSummary adapter={report.initial_adapter ?? run.initial_adapter} />}
      {audit && <DataAuditSummary audit={audit} />}
      {tasks.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <Label htmlFor="experiment-result-task">{t("academy.experiments.category")}</Label>
          <select id="experiment-result-task" value={selectedTask} onChange={(event) => setTask(event.target.value)}
            className="max-w-full rounded-md border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-2 text-sm">
            <option value="total">{t("academy.campaigns.quality.total")}</option>
            {tasks.map((key) => <option key={key} value={key}>{key}</option>)}
          </select>
        </div>
      )}
      <Comparison report={report} task={selectedTask} />
      {report.artifacts?.length ? (
        <ul className="space-y-1 text-sm">
          {report.artifacts.map((artifact, index) => (
            <li key={`${artifact.kind}-${artifact.sha256 ?? index}`}>
              {artifact.kind} · {t(artifact.available ? "academy.experiments.available" : "academy.experiments.unavailable")}
              {typeof artifact.bytes === "number" ? ` · ${artifact.bytes.toLocaleString()} B` : ""}
            </li>
          ))}
        </ul>
      ) : null}
      {report.cases?.map((item) => (
        <details className="rounded-lg border border-[color:var(--ui-border)] p-3" key={item.case_id}>
          <summary className="cursor-pointer text-sm">{item.case_id}</summary>
          <div className="mt-3 space-y-3">
            <Conversation messages={item.messages} />
            <div className="grid gap-3 lg:grid-cols-2">
              <Answer title={t("academy.experiments.base")} answer={item.base} verdict={report.verdicts?.base?.[item.case_id]} />
              <Answer title={t("academy.experiments.candidate")} answer={item.candidate} verdict={report.verdicts?.candidate?.[item.case_id]} />
            </div>
          </div>
        </details>
      ))}
    </section>
  );
}

function parseJudgments(source: string): Record<string, unknown>[] {
  const text = source.trim();
  let data: unknown;
  try {
    const parsed: unknown = JSON.parse(text);
    if (typeof parsed === "object" && parsed !== null && "judgments" in parsed) data = parsed.judgments;
    else data = Array.isArray(parsed) ? parsed : [parsed];
  } catch {
    data = text.split(/\r?\n/).filter((line) => line.trim()).map((line) => JSON.parse(line));
  }
  if (!Array.isArray(data) || !data.length || data.some((item) => !item || typeof item !== "object" || Array.isArray(item))) {
    throw new Error("expected judgment objects");
  }
  return data;
}

interface ReviewProps {
  readonly runId: string;
  readonly disabled: boolean;
  readonly onSubmit: (judgments: Record<string, unknown>[]) => Promise<boolean>;
}

export function ExperimentReviewPanel({ runId, disabled, onSubmit }: ReviewProps) {
  const t = useTranslation();
  const [review, setReview] = useState<ExperimentReview | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [fileError, setFileError] = useState(false);
  const [reading, setReading] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const abort = new AbortController();
    void getExperimentReview(runId, abort.signal)
      .then((result) => { if (!abort.signal.aborted) setReview(result); })
      .catch(() => { if (!abort.signal.aborted) setLoadError(true); });
    return () => abort.abort();
  }, [runId, retry]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled || reading) return;
    const file = new FormData(event.currentTarget).get("judgments");
    if (!(file instanceof File) || !file.size) {
      setFileError(true);
      return;
    }
    setReading(true);
    setFileError(false);
    try {
      await onSubmit(parseJudgments(await file.text()));
    } catch {
      setFileError(true);
    } finally {
      setReading(false);
    }
  }

  if (!review && !loadError) return <p className="text-sm text-hint">{t("academy.experiments.loadingReview")}</p>;
  if (loadError) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <p role="alert" className="text-sm text-red-400">{t("academy.experiments.reviewError")}</p>
        <Button type="button" size="sm" variant="outline" onClick={() => { setLoadError(false); setRetry((value) => value + 1); }}>
          {t("academy.common.retry")}
        </Button>
      </div>
    );
  }

  return (
    <section className="space-y-3">
      <h4 className="font-semibold">{t("academy.experiments.review")}</h4>
      <p className="text-sm text-hint">{t("academy.experiments.reviewHint")}</p>
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => downloadJson(`experiment-${runId}-review.json`, review)}
      >
        {t("academy.experiments.downloadReview")}
      </Button>
      {review?.answers.map((item) => (
        <details className="rounded-lg border border-[color:var(--ui-border)] p-3" key={item.case.record_id}>
          <summary className="cursor-pointer text-sm">{item.case.record_id}</summary>
          <div className="mt-3 space-y-3">
            <Conversation messages={item.case.messages} />
            {item.case.criteria?.map((criterion) => (
              <p key={criterion.id} className="text-sm text-hint">{criterion.id} · {criterion.description ?? criterion.kind}</p>
            ))}
            <div className="grid gap-3 lg:grid-cols-2">
              {Object.entries(item.answers).map(([label, answer]) => <Answer key={label} title={label} answer={answer} />)}
            </div>
          </div>
        </details>
      ))}
      <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => void submit(event)}>
        <div className="space-y-1">
          <Label htmlFor="experiment-judgments">{t("academy.experiments.judgmentsFile")}</Label>
          <Input id="experiment-judgments" name="judgments" type="file" accept=".json,.jsonl,application/json" required disabled={disabled || reading} />
        </div>
        <Button type="submit" disabled={disabled || reading}>{t("academy.experiments.submitJudgments")}</Button>
      </form>
      {fileError && <p role="alert" className="text-sm text-red-400">{t("academy.experiments.judgmentsError")}</p>}
    </section>
  );
}
