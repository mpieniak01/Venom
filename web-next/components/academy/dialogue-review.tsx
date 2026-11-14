"use client";

import { useRef, useState, type ReactNode } from "react";
import { evaluateExperimentDialogue, type DialogueJudgeResult } from "@/lib/academy-experiments-api";
import { useLanguage, useTranslation } from "@/lib/i18n";

type JudgeState = DialogueJudgeResult | "pending" | "failed";

interface Props {
  readonly children: ReactNode;
  readonly recordId: string;
  readonly runId: string;
  readonly checkpointStep?: number;
  readonly judgeEnabled: boolean;
}

export function DialogueReview({ children, recordId, runId, checkpointStep, judgeEnabled }: Props) {
  const t = useTranslation();
  const [state, setState] = useState<JudgeState>();
  const requested = useRef(false);

  async function evaluate() {
    if (!judgeEnabled || requested.current) return;
    requested.current = true;
    setState("pending");
    try {
      setState(await evaluateExperimentDialogue(runId, recordId, checkpointStep));
    } catch {
      setState("failed");
    }
  }

  return (
    <details
      className="rounded-lg border border-[color:var(--ui-border)] p-3"
      onToggle={(event) => { if (event.currentTarget.open) void evaluate(); }}
    >
      <summary className="cursor-pointer text-sm">
        {recordId}
        {judgeEnabled && <span className="ml-2 text-xs text-hint">{t("academy.experiments.judge.paid")}</span>}
      </summary>
      <div className="mt-3 space-y-3">
        {children}
        {state && <JudgeSuggestions state={state} />}
      </div>
    </details>
  );
}

function JudgeSuggestions({ state }: { readonly state: JudgeState }) {
  const { t, language } = useLanguage();
  const usd = new Intl.NumberFormat(language, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 8,
  });
  if (state === "pending") {
    return <p role="status" className="text-sm text-hint">{t("academy.experiments.judge.pending")}</p>;
  }
  if (state === "failed") {
    return <p role="status" className="text-sm text-hint">{t("academy.experiments.judge.failed")}</p>;
  }
  return (
    <section className="space-y-2 border-t border-[color:var(--ui-border)] pt-3" aria-label={t("academy.experiments.judge.suggestion")}>
      <h5 className="text-sm font-medium">{t("academy.experiments.judge.suggestion")}</h5>
      <dl className="space-y-2 text-sm">
        {Object.entries(state.answers).map(([label, answer]) => (
          <div key={label}>
            <dt className="font-medium">
              {label} · {t(answer.verdict ? (
                answer.verdict.pass ? "academy.experiments.judge.pass" : "academy.experiments.judge.reject"
              ) : "academy.experiments.judge.failed")}
            </dt>
            {answer.verdict?.critical && <dd>{t("academy.experiments.judge.critical")}</dd>}
            {answer.verdict && <dd className="break-words">{answer.verdict.reason}</dd>}
            <dd className="text-hint">
              {answer.cost_usd === null ? t("academy.experiments.judge.unknownCost") : (
                <>{t("academy.experiments.judge.cost")} {usd.format(Number(answer.cost_usd))}</>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
