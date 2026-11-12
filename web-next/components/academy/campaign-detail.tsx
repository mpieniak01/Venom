"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  applyCampaignRetention,
  campaignReportUrl,
  getCampaignRetentionPlan,
  type Campaign,
  type CampaignRetentionPlan,
  type CampaignTrial,
} from "@/lib/academy-campaign-api";
import { useLanguage, useTranslation } from "@/lib/i18n";
import { OPTUNA_PARAMETERS, OptunaPlanSummary } from "./campaign-optuna";

const ACTIVE = new Set(["running", "awaiting_review", "stopping", "interrupted"]);
const CAN_RESUME = new Set(["interrupted", "blocked", "stopped"]);
const STATUSES = new Set([
  "planned", "pending", "queued", "running", "awaiting_review", "stopping",
  "interrupted", "blocked", "stopped", "succeeded", "failed", "timed_out", "skipped", "pruned", "cancelled",
]);

export function campaignIsActive(status: string) {
  return ACTIVE.has(status);
}

export function CampaignStatus({ status }: { readonly status: string }) {
  const t = useTranslation();
  return <span role="status">{t(`academy.campaigns.status.${STATUSES.has(status) ? status : "unknown"}`)}</span>;
}

function displayBytes(bytes: number, language: string) {
  return new Intl.NumberFormat(language, { style: "unit", unit: "megabyte", maximumFractionDigits: 1 }).format(bytes / 1_000_000);
}

function Retention({ campaignId, disabled, onChanged }: {
  readonly campaignId: string;
  readonly disabled: boolean;
  readonly onChanged: () => void;
}) {
  const { t, language } = useLanguage();
  const [plan, setPlan] = useState<CampaignRetentionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const [removedBytes, setRemovedBytes] = useState<number | null>(null);

  async function preview() {
    setBusy(true);
    setError(false);
    setRemovedBytes(null);
    try {
      setPlan(await getCampaignRetentionPlan(campaignId));
    } catch {
      setPlan(null);
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!plan || !plan.files.length || busy || disabled) return;
    setBusy(true);
    setError(false);
    try {
      const receipt = await applyCampaignRetention(campaignId, plan.plan_sha256);
      setRemovedBytes(receipt.removed_bytes);
      setPlan(null);
      onChanged();
    } catch {
      setPlan(null);
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3">
      <h4 className="font-medium">{t("academy.campaigns.retention")}</h4>
      <Button type="button" size="sm" variant="outline" disabled={disabled || busy} onClick={() => void preview()}>
        {t("academy.campaigns.previewRetention")}
      </Button>
      {error && <p role="alert" className="text-sm text-red-400">{t("academy.campaigns.retentionError")}</p>}
      {removedBytes !== null && (
        <p role="status" className="text-sm">{t("academy.campaigns.removed")} {displayBytes(removedBytes, language)}</p>
      )}
      {plan && (plan.files.length ? (
        <div className="space-y-3 rounded-lg border border-[color:var(--ui-border)] p-3">
          <p className="text-sm">{t("academy.campaigns.recoverable")} {displayBytes(plan.bytes, language)}</p>
          <ul className="max-h-60 space-y-1 overflow-auto text-xs">
            {plan.files.map((file) => (
              <li key={`${file.run_id}-${file.path}`} className="break-all">
                {file.run_id} · {file.path} · {displayBytes(file.size_bytes, language)}
              </li>
            ))}
          </ul>
          <Button type="button" size="sm" variant="warning" disabled={disabled || busy} onClick={() => void apply()}>
            {t("academy.campaigns.applyRetention")}
          </Button>
        </div>
      ) : <p className="text-sm text-hint">{t("academy.campaigns.noRetentionFiles")}</p>)}
    </section>
  );
}

function OptunaTrialSummary({ trial }: { readonly trial: CampaignTrial }) {
  const { t, language } = useLanguage();
  const formatter = new Intl.NumberFormat(language, { maximumSignificantDigits: 8 });
  const duplicate = trial.error === "campaign_duplicate_suggestion";

  return (
    <div className="space-y-1 pl-3 text-xs text-hint">
      {typeof trial.optuna_trial_number === "number" && (
        <p>{t("academy.campaigns.optuna.trial")} {trial.optuna_trial_number}
          {trial.optuna_trial_state && <> · {t("academy.campaigns.optuna.state." + trial.optuna_trial_state)}</>}
        </p>
      )}
      {trial.recipe && (
        <dl className="flex flex-wrap gap-x-3 gap-y-1">
          {OPTUNA_PARAMETERS.map(({ key, label }) => {
            const value = trial.recipe?.[key];
            return typeof value === "number" ? (
              <div key={key} className="flex gap-1">
                <dt>{t(label)}</dt><dd>{formatter.format(value)}</dd>
              </div>
            ) : null;
          })}
        </dl>
      )}
      {duplicate && <p>{t("academy.campaigns.optuna.duplicate")}</p>}
    </div>
  );
}

interface CampaignDetailProps {
  readonly campaign: Campaign;
  readonly disabled: boolean;
  readonly optunaAvailable: boolean;
  readonly onAction: (action: "start" | "stop" | "resume") => void;
  readonly onOpenRun: (runId: string) => void;
  readonly onChanged: () => void;
}

export function CampaignDetail({ campaign, disabled, optunaAvailable, onAction, onOpenRun, onChanged }: CampaignDetailProps) {
  const { t, language } = useLanguage();
  const { budget, selection, variants, strategy } = campaign.plan;
  const optuna = strategy === "optuna";
  const launchDisabled = disabled || (optuna && !optunaAvailable);
  const displayNumber = new Intl.NumberFormat(language, { maximumFractionDigits: 1 });
  const displayDelta = new Intl.NumberFormat(language, { maximumFractionDigits: 1, signDisplay: "exceptZero" });
  const trialLimit = `${campaign.trial_index} / ${variants.length}`;
  const planned = campaign.status === "planned";
  const active = campaignIsActive(campaign.status);
  const canStop = (active && campaign.status !== "stopping") || campaign.status === "blocked";
  const canResume = CAN_RESUME.has(campaign.status) && campaign.elapsed_seconds < budget.max_seconds;

  function delta(value?: number) {
    return typeof value === "number" ? displayDelta.format(value * 100) : t("academy.experiments.unavailable");
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="break-all font-semibold">{campaign.campaign_id}</h3>
        <p className="text-sm"><CampaignStatus status={campaign.status} /></p>
      </div>
      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        <div><dt className="text-hint">{t("academy.experiments.profile")}</dt><dd>{campaign.plan.profile_id}</dd></div>
        <div>
          <dt className="text-hint">{t("academy.campaigns.strategy")}</dt>
          <dd>{t(optuna ? "academy.campaigns.optuna.name" : "academy.campaigns.fixed")}</dd>
        </div>
        <div><dt className="text-hint">{t("academy.campaigns.trials")}</dt><dd>{trialLimit}</dd></div>
        <div><dt className="text-hint">{t("academy.campaigns.budget.max_seconds")}</dt><dd>{displayNumber.format(campaign.elapsed_seconds)} / {displayNumber.format(budget.max_seconds)}</dd></div>
        <div><dt className="text-hint">{t("academy.campaigns.budget.max_updates")}</dt><dd>{displayNumber.format(campaign.used_updates)} / {displayNumber.format(budget.max_updates)}</dd></div>
        <div><dt className="text-hint">{t("academy.campaigns.budget.max_tokens")}</dt><dd>{displayNumber.format(campaign.used_tokens)} / {displayNumber.format(budget.max_tokens)}</dd></div>
        <div><dt className="text-hint">{t("academy.campaigns.artifactSize")}</dt><dd>{displayBytes(campaign.artifact_bytes, language)} / {displayBytes(budget.max_artifact_bytes, language)}</dd></div>
        <div><dt className="text-hint">{t("academy.campaigns.budget.trial_seconds")}</dt><dd>{displayNumber.format(budget.trial_seconds)}</dd></div>
        <div><dt className="text-hint">{t("academy.campaigns.budget.max_retries")}</dt><dd>{campaign.retries} / {budget.max_retries}</dd></div>
        <div><dt className="text-hint">{t("academy.campaigns.freeSpace")}</dt><dd>{displayBytes(budget.min_free_bytes, language)}</dd></div>
      </dl>
      <dl className="flex flex-wrap gap-3 text-sm">
        <div><dt className="text-hint">{t("academy.campaigns.minUsable")}</dt><dd>{delta(selection.min_usable_delta)}</dd></div>
        <div><dt className="text-hint">{t("academy.campaigns.maxCritical")}</dt><dd>{delta(selection.max_critical_delta)}</dd></div>
        <div><dt className="text-hint">{t("academy.campaigns.reviewMode")}</dt><dd>{t(campaign.plan.review_mode === "manual" ? "academy.campaigns.manualReview" : "academy.campaigns.automaticReview")}</dd></div>
        <div><dt className="text-hint">{t("academy.campaigns.retention")}</dt><dd>{t(campaign.plan.retention === "keep_all" ? "academy.campaigns.keepAll" : "academy.campaigns.discardRejected")}</dd></div>
      </dl>
      {optuna && <OptunaPlanSummary plan={campaign.plan} />}
      {campaign.error && <p role="alert" className="break-all text-sm text-red-400">{campaign.error}</p>}
      {campaign.selected_run_id && (
        <p className="break-all text-sm font-medium">{t("academy.campaigns.selected")} {campaign.selected_run_id}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {planned && <Button type="button" disabled={launchDisabled} onClick={() => onAction("start")}>{t("academy.campaigns.start")}</Button>}
        {canStop && <Button type="button" variant="outline" disabled={disabled} onClick={() => onAction("stop")}>{t("academy.campaigns.stop")}</Button>}
        {canResume && <Button type="button" variant="outline" disabled={launchDisabled} onClick={() => onAction("resume")}>{t("academy.campaigns.resume")}</Button>}
        <Button asChild variant="outline">
          <a href={campaignReportUrl(campaign.campaign_id)} download={`campaign-${campaign.campaign_id}.json`}>
            {t("academy.experiments.downloadReport")}
          </a>
        </Button>
      </div>
      {planned && (
        <details className="text-sm">
          <summary className="cursor-pointer">{t("academy.campaigns.chatStart")}</summary>
          <code className="break-all">/academy start {campaign.campaign_id} {campaign.plan.plan_sha256}</code>
        </details>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead><tr className="border-b border-[color:var(--ui-border)]">
            <th scope="col" className="py-2 pr-3">{t("academy.experiments.runId")}</th>
            <th scope="col" className="px-3 py-2">{t("academy.campaigns.state")}</th>
            <th scope="col" className="px-3 py-2">{t("academy.campaigns.qualityDelta")}</th>
            <th scope="col" className="px-3 py-2">{t("academy.campaigns.criticalDelta")}</th>
          </tr></thead>
          <tbody>
            {campaign.trials.map((trial, index) => {
              const variant = variants[index];
              return (
                <tr key={trial.run_id} className="border-b border-[color:var(--ui-border)]">
                  <th scope="row" className="py-2 pr-3 font-normal">
                    <Button type="button" size="sm" variant="ghost" disabled={trial.status === "pending" || trial.status === "skipped"} onClick={() => onOpenRun(trial.run_id)}>
                      {trial.run_id}
                    </Button>
                    {optuna && <OptunaTrialSummary trial={trial} />}
                    {!optuna && variant && <p className="pl-3 text-xs text-hint">
                      {t("academy.experiments.rank")} {variant.recipe.rank} · {t("academy.experiments.learningRate")} {variant.recipe.learning_rate}
                      {" · "}{t("academy.campaigns.plannedWorkload")} {displayNumber.format(variant.workload.updates)} / {displayNumber.format(variant.workload.tokens)}
                    </p>}
                  </th>
                  <td className="px-3 py-2"><CampaignStatus status={trial.status} /></td>
                  <td className="px-3 py-2">{delta(trial.usable_delta)}</td>
                  <td className="px-3 py-2">{delta(trial.critical_delta)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!active && !planned && campaign.plan.retention === "discard_rejected" && (
        <Retention campaignId={campaign.campaign_id} disabled={disabled} onChanged={onChanged} />
      )}
    </div>
  );
}
