"use client";

import { useRef, useState, type ReactNode } from "react";
import { evaluateExperimentDialogue, type DialogueJudgeResult } from "@/lib/academy-experiments-api";
import { useLanguage, useTranslation } from "@/lib/i18n";

const JUDGE = "academy.experiments.judge.";

type JudgeState = DialogueJudgeResult | "pending" | "failed";

interface Props {
  readonly children: ReactNode;
  readonly recordId: string;
  readonly runId: string;
  readonly checkpointStep?: number;
  readonly judgeEnabled: boolean;
  readonly canReadJudge?: boolean;
}

export function DialogueReview({ children, recordId, runId, checkpointStep, judgeEnabled, canReadJudge = judgeEnabled }: Props) {
  const t = useTranslation();
  const [state, setState] = useState<JudgeState>();
  const requested = useRef(false);

  async function evaluate() {
    if (!canReadJudge || requested.current) return;
    requested.current = true;
    setState("pending");
    try {
      const result = await evaluateExperimentDialogue(runId, recordId, checkpointStep, !judgeEnabled || state === "failed");
      setState(Object.keys(result.answers).length ? result : undefined);
      requested.current = !judgeEnabled || !Object.values(result.answers).some((answer) => answer.retryable);
    } catch {
      requested.current = false;
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
        {judgeEnabled && <span className="ml-2 text-xs text-hint">{t(JUDGE + "paid")}</span>}
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
  if (typeof state === "string") {
    return <output className="block text-sm text-hint">{t(JUDGE + state)}</output>;
  }
  return (
    <section className="space-y-2 border-t border-[color:var(--ui-border)] pt-3" aria-label={t(JUDGE + "suggestion")}>
      <h5 className="text-sm font-medium">{t(JUDGE + "suggestion")}</h5>
      <dl className="space-y-2 text-sm">
        {Object.entries(state.answers).map(([label, answer]) => {
          const verdict = answer.verdict;
          let verdictKey = "failed";
          if (verdict) verdictKey = verdict.pass ? "pass" : "reject";
          return (
            <div key={label}>
              <dt className="font-medium">{label} · {t(JUDGE + verdictKey)}</dt>
              {verdict?.critical && <dd>{t(JUDGE + "critical")}</dd>}
              {verdict && <dd className="break-words">{verdict.reason}</dd>}
              <dd className="text-hint">
                {answer.cost_usd === null ? t(JUDGE + "unknownCost") : (
                  <>{t(JUDGE + "cost")} {usd.format(Number(answer.cost_usd))}</>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
