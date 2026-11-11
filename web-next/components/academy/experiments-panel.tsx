"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api-client";
import {
  getExperimentLogs,
  listExperimentProfiles,
  listExperimentRuns,
  startExperiment,
  submitExperimentJudgments,
  updateExperiment,
  type ExperimentAction,
  type ExperimentProfile,
  type ExperimentRun,
} from "@/lib/academy-experiments-api";
import { useLanguage, useTranslation } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { ExperimentForm } from "./experiment-form";
import { ExperimentResult, ExperimentReviewPanel } from "./experiment-results";

const ACTIVE = new Set(["queued", "running"]);
const INTERRUPTED = new Set(["failed", "stopped", "timed_out"]);
const STATUS_LABELS = {
  queued: "academy.experiments.status.queued",
  running: "academy.experiments.status.running",
  awaiting_review: "academy.experiments.status.awaiting_review",
  succeeded: "academy.experiments.status.succeeded",
  failed: "academy.experiments.status.failed",
  stopped: "academy.experiments.status.stopped",
  timed_out: "academy.experiments.status.timed_out",
} as const;
const STAGE_LABELS = {
  preflight: "academy.experiments.stage.preflight",
  train: "academy.experiments.stage.train",
  generate: "academy.experiments.stage.generate",
  score: "academy.experiments.stage.score",
  commit: "academy.experiments.stage.commit",
} as const;

const SECTION_CLASS = "space-y-4 rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4 sm:p-5";
const POLL_MS = 3000;

function RunStatus({ run }: { readonly run: ExperimentRun }) {
  const t = useTranslation();
  const status = STATUS_LABELS[run.status as keyof typeof STATUS_LABELS];
  const stage = STAGE_LABELS[run.stage as keyof typeof STAGE_LABELS];
  return (
    <span role="status">
      {status ? t(status) : t("academy.experiments.status.unknown")}
      {stage && ACTIVE.has(run.status) ? ` · ${t(stage)}` : ""}
    </span>
  );
}

function ExperimentLogs({ run }: { readonly run: ExperimentRun }) {
  const t = useTranslation();
  const [logs, setLogs] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const abort = new AbortController();
    let timeout: ReturnType<typeof setTimeout>;
    async function read() {
      try {
        const result = await getExperimentLogs(run.run_id, abort.signal);
        if (abort.signal.aborted) return;
        setLogs(result.logs);
        setError(false);
      } catch {
        if (!abort.signal.aborted) setError(true);
      }
      if (!abort.signal.aborted && ACTIVE.has(run.status)) timeout = setTimeout(() => void read(), POLL_MS);
    }
    void read();
    return () => { abort.abort(); clearTimeout(timeout); };
  }, [run.run_id, run.status]);

  return (
    <div className="space-y-2">
      {error && <p role="alert" className="text-sm text-red-400">{t("academy.experiments.logsError")}</p>}
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-black/20 p-3 text-xs">
        {logs ?? t("academy.experiments.loadingLogs")}
      </pre>
    </div>
  );
}

interface RunDetailProps {
  readonly run: ExperimentRun;
  readonly disabled: boolean;
  readonly onAction: (action: ExperimentAction) => void;
  readonly onJudgments: (judgments: Record<string, unknown>[]) => Promise<boolean>;
}

function RunDetail({ run, disabled, onAction, onJudgments }: RunDetailProps) {
  const { t, language } = useLanguage();
  const [showLogs, setShowLogs] = useState(false);
  const interrupted = INTERRUPTED.has(run.status);
  const hasCheckpoint = typeof run.checkpoint_step === "number";
  const canResume = run.actions?.resume ?? (interrupted && run.resume_available);
  const elapsed = run.elapsed_seconds;

  return (
    <section className={SECTION_CLASS}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="break-all font-semibold">{run.run_id}</h3>
        <p className="text-sm"><RunStatus run={run} /></p>
      </div>
      <dl className="flex flex-wrap gap-4 text-sm">
        <div><dt className="text-hint">{t("academy.experiments.attempt")}</dt><dd>{run.attempt}</dd></div>
        {Number.isFinite(run.updated_at) && (
          <div>
            <dt className="text-hint">{t("academy.experiments.updated")}</dt>
            <dd>{new Date(run.updated_at * 1000).toLocaleString(language)}</dd>
          </div>
        )}
        {typeof elapsed === "number" && Number.isFinite(elapsed) && (
          <div>
            <dt className="text-hint">{t("academy.experiments.elapsed")}</dt>
            <dd>{new Intl.NumberFormat(language, { style: "unit", unit: "second", maximumFractionDigits: 0 }).format(elapsed)}</dd>
          </div>
        )}
        <div>
          <dt className="text-hint">{t("academy.experiments.checkpoint")}</dt>
          <dd>{hasCheckpoint ? run.checkpoint_step : t("academy.experiments.noCheckpoint")}</dd>
        </div>
        <div>
          <dt className="text-hint">{t("academy.experiments.resume")}</dt>
          <dd>{t(run.resume_available ? "academy.experiments.available" : "academy.experiments.unavailable")}</dd>
        </div>
      </dl>
      {run.error && (
        <div className="space-y-1 text-sm text-red-400">
          <p>{t("academy.experiments.runError")}</p>
          <pre className="max-h-28 overflow-auto whitespace-pre-wrap break-words">{run.error}</pre>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {(run.actions?.stop ?? ACTIVE.has(run.status)) && (
          <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => onAction("stop")}>
            {t("academy.experiments.stop")}
          </Button>
        )}
        {(interrupted || canResume) && (
          <Button type="button" size="sm" variant="outline" disabled={disabled || !canResume} onClick={() => onAction("resume")}>
            {t("academy.experiments.resume")}
          </Button>
        )}
        {(run.actions?.evaluate ?? (interrupted && hasCheckpoint)) && (
          <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => onAction("evaluate")}>
            {t("academy.experiments.evaluate")}
          </Button>
        )}
        <Button type="button" size="sm" variant="outline" aria-pressed={showLogs} onClick={() => setShowLogs((current) => !current)}>
          {t("academy.experiments.logs")}
        </Button>
      </div>
      {showLogs && <ExperimentLogs run={run} />}
      {(run.actions?.review ?? run.status === "awaiting_review") && <ExperimentReviewPanel runId={run.run_id} disabled={disabled} onSubmit={onJudgments} />}
      {(run.status === "succeeded" || run.report) && <ExperimentResult run={run} />}
    </section>
  );
}

export function ExperimentsPanel({ initialRunId = "" }: { readonly initialRunId?: string }) {
  const t = useTranslation();
  const [profiles, setProfiles] = useState<ExperimentProfile[]>([]);
  const [runs, setRuns] = useState<ExperimentRun[]>([]);
  const [profilesLoaded, setProfilesLoaded] = useState(false);
  const [runsLoaded, setRunsLoaded] = useState(false);
  const [profilesFailed, setProfilesFailed] = useState(false);
  const [runsFailed, setRunsFailed] = useState(false);
  const [actionError, setActionError] = useState<"conflict" | "failed" | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState(initialRunId);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let inFlight = false;
    let active = false;

    async function readRuns() {
      if (abort.signal.aborted || inFlight) return;
      clearTimeout(timer);
      inFlight = true;
      try {
        const next = await listExperimentRuns(abort.signal);
        if (abort.signal.aborted) return;
        setRuns(next);
        setRunsFailed(false);
        active = next.some((run) => ACTIVE.has(run.status));
      } catch {
        if (!abort.signal.aborted) setRunsFailed(true);
      } finally {
        inFlight = false;
        if (!abort.signal.aborted) {
          setRunsLoaded(true);
          if (active) timer = setTimeout(refreshVisible, POLL_MS);
        }
      }
    }

    function refreshVisible() {
      if (document.visibilityState !== "hidden") void readRuns();
    }

    void listExperimentProfiles(abort.signal)
      .then((next) => {
        if (abort.signal.aborted) return;
        setProfiles(next);
        setProfilesFailed(false);
      })
      .catch(() => { if (!abort.signal.aborted) setProfilesFailed(true); })
      .finally(() => { if (!abort.signal.aborted) setProfilesLoaded(true); });
    void readRuns();
    document.addEventListener("visibilitychange", refreshVisible);
    return () => {
      abort.abort();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", refreshVisible);
    };
  }, [refresh]);

  async function mutate(operation: () => Promise<ExperimentRun>) {
    if (busy) return false;
    setBusy(true);
    setActionError(null);
    try {
      const next = await operation();
      setRuns((current) => [next, ...current.filter((item) => item.run_id !== next.run_id)]);
      setSelectedId(next.run_id);
      setRefresh((value) => value + 1);
      return true;
    } catch (error) {
      setActionError(error instanceof ApiError && error.status === 409 ? "conflict" : "failed");
      return false;
    } finally {
      setBusy(false);
    }
  }

  const selected = runs.find((run) => run.run_id === selectedId) ?? runs[0];
  const hasActive = runs.some((run) => ACTIVE.has(run.status));
  return (
    <div className="space-y-4">
      <section className={SECTION_CLASS}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold">{t("academy.experiments.title")}</h3>
          <Button type="button" variant="outline" size="sm" onClick={() => setRefresh((value) => value + 1)}>
            {t("academy.common.refresh")}
          </Button>
        </div>
        {(profilesFailed || runsFailed) && <p role="alert" className="text-sm text-red-400">{t("academy.experiments.loadError")}</p>}
        {!(profilesLoaded && runsLoaded) ? (
          <p className="text-sm text-hint">{t("academy.experiments.loading")}</p>
        ) : (
          <ExperimentForm profiles={profiles} disabled={busy || hasActive || profilesFailed || runsFailed} onStart={(request) => mutate(() => startExperiment(request))} />
        )}
        {actionError && <p role="alert" className="text-sm text-red-400">{t(actionError === "conflict" ? "academy.experiments.conflict" : "academy.experiments.actionError")}</p>}
      </section>
      {runsLoaded && (
        <section className={SECTION_CLASS}>
          <h3 className="font-semibold">{t("academy.experiments.history")}</h3>
          {runs.length ? (
            <ul className="space-y-2">
              {runs.map((run) => (
                <li key={run.run_id}>
                  <Button
                    type="button"
                    variant={selected?.run_id === run.run_id ? "secondary" : "outline"}
                    className="h-auto w-full flex-wrap justify-between gap-2 text-left"
                    aria-pressed={selected?.run_id === run.run_id}
                    onClick={() => setSelectedId(run.run_id)}
                  >
                    <span className="break-all">{run.run_id}</span>
                    <span className="text-xs text-hint"><RunStatus run={run} /></span>
                  </Button>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-hint">{t("academy.experiments.noRuns")}</p>}
        </section>
      )}
      {selected && (
        <RunDetail
          key={selected.run_id}
          run={selected}
          disabled={busy || runsFailed}
          onAction={(action) => void mutate(() => updateExperiment(selected.run_id, action))}
          onJudgments={(judgments) => mutate(() => submitExperimentJudgments(selected.run_id, judgments))}
        />
      )}
    </div>
  );
}
