"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  controlRemoteTextCampaign,
  listRemoteTextCampaigns,
  planRemoteTextCampaign,
  remoteTextEvidenceUrl,
  type RemoteTextCampaign,
} from "@/lib/academy-campaign-api";
import type { ExperimentInitialAdapter, ExperimentProfile } from "@/lib/academy-experiments-api";
import { ApiError } from "@/lib/api-client";
import { useTranslation } from "@/lib/i18n";
import { CampaignForm } from "./campaign-form";

const ACTIONABLE = new Set(["queued", "running", "finalizing"]);
const MICROS = 1_000_000;

interface PanelProps {
  readonly profiles: ExperimentProfile[];
  readonly adapters: ExperimentInitialAdapter[];
  readonly adaptersFailed: boolean;
  readonly optunaAvailable: boolean;
}

export function RemoteTextCampaigns({ profiles, adapters, adaptersFailed, optunaAvailable }: PanelProps) {
  const t = useTranslation();
  const [campaigns, setCampaigns] = useState<RemoteTextCampaign[]>([]);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [pollFailed, setPollFailed] = useState(false);
  const [planId, setPlanId] = useState("");
  const [cost, setCost] = useState("");
  const [testHash, setTestHash] = useState("");
  const [calibrationHash, setCalibrationHash] = useState("");
  const budget = Math.round(Number(cost) * MICROS);
  const sha = /^[a-f0-9]{64}$/;
  const validPins = (!testHash && !calibrationHash) || (sha.test(testHash) && sha.test(calibrationHash));
  const valid = /^[a-f0-9]{32}$/.test(planId) && budget >= 1 && budget <= 1000 * MICROS && validPins;

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await listRemoteTextCampaigns(controller.signal);
        if (!controller.signal.aborted) {
          setCampaigns(result.campaigns);
          setPollFailed(false);
        }
      } catch {
        if (!controller.signal.aborted) setPollFailed(true);
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
      }
    }
    if (!busy) void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [busy]);

  async function act(operation: () => Promise<RemoteTextCampaign>) {
    setBusy(true);
    setFailed(null);
    try {
      const campaign = await operation();
      setCampaigns((current) => [
        campaign,
        ...current.filter((item) => item.campaign_id !== campaign.campaign_id),
      ]);
      return true;
    } catch (error) {
      const code = error instanceof ApiError
        ? (error.data as { detail?: { code?: string } } | null)?.detail?.code
        : undefined;
      const key = `academy.remoteText.errors.${code}`;
      setFailed(code && t(key) !== key ? key : "academy.remoteText.error");
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-4">
      <p className="text-sm text-hint">{t("academy.remoteText.prepared")}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="remote-text-vm">{t("academy.remoteText.environment")}</Label>
          <Input id="remote-text-vm" value={planId} maxLength={32} disabled={busy}
            onChange={(event) => setPlanId(event.currentTarget.value.trim())} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="remote-text-cost">{t("academy.remoteText.costLimit")}</Label>
          <Input id="remote-text-cost" type="number" min={0.000001} max={1000}
            step={0.000001} value={cost} disabled={busy} onChange={(event) => setCost(event.currentTarget.value)} />
        </div>
      </div>
      <details className="space-y-3">
        <summary className="cursor-pointer">{t("academy.remoteText.finalTest")}</summary>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="remote-text-holdout">{t("academy.remoteText.testHash")}</Label>
            <Input id="remote-text-holdout" value={testHash} maxLength={64} disabled={busy}
              onChange={(event) => setTestHash(event.currentTarget.value.trim())} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="remote-text-calibration">{t("academy.remoteText.calibrationHash")}</Label>
            <Input id="remote-text-calibration" value={calibrationHash} maxLength={64} disabled={busy}
              onChange={(event) => setCalibrationHash(event.currentTarget.value.trim())} />
          </div>
        </div>
      </details>
      <CampaignForm profiles={profiles} adapters={adapters} adaptersFailed={adaptersFailed}
        optunaAvailable={optunaAvailable} remoteText disabled={busy || !valid}
        onDiscardDraft={() => undefined}
        onPlan={(campaign) => act(() => planRemoteTextCampaign(campaign, planId, budget, testHash, calibrationHash))} />
      {(failed || pollFailed) && <p role="alert">{t(failed ?? "academy.remoteText.error")}</p>}
      <ul className="space-y-3">
        {campaigns.map((campaign) => (
          <li key={campaign.campaign_id}>
            <RemoteTextResult campaign={campaign} busy={busy}
              onAction={(action) => void act(() => controlRemoteTextCampaign(campaign, action))} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function RemoteTextResult({ campaign, busy, onAction }: {
  readonly campaign: RemoteTextCampaign;
  readonly busy: boolean;
  readonly onAction: (action: "start" | "stop") => void;
}) {
  const t = useTranslation();
  const best = campaign.result?.best_observed;
  const measured = campaign.cost?.billed_microusd;
  const estimate = campaign.cost?.estimated_microusd ?? campaign.quote.estimated_microusd;
  const localTime = (timestamp: number) => new Date(timestamp * 1000).toLocaleString();
  const usd = (micros: number) => (micros / MICROS).toLocaleString(undefined, {
    style: "currency", currency: "USD", maximumFractionDigits: 6,
  });
  return (
    <article className="space-y-2 rounded-lg border border-[color:var(--ui-border)] p-3">
      <h4 className="break-all font-medium">{campaign.campaign_id}</h4>
      <p>{t(`academy.remoteText.status.${campaign.status}`)} · {t(`academy.remoteText.cleanup.${campaign.cleanup.state}`)}</p>
      <p>{t("academy.remoteText.estimate")} {usd(estimate)}
        {measured != null && <> · {t("academy.remoteText.billed")} {usd(measured)}</>}</p>
      {campaign.deadline_at != null && <p>{t("academy.remoteText.deadline")} {localTime(campaign.deadline_at)}</p>}
      {campaign.last_sync_at != null && <p>{t("academy.remoteText.synced")} {localTime(campaign.last_sync_at)}</p>}
      {campaign.remote && <p>{t("academy.remoteText.progress")} {campaign.remote.trial_index}/{campaign.remote.trials.length}</p>}
      {campaign.remote?.extension_decision && <p>
        {t(`academy.remoteText.extension.${campaign.remote.extension_decision.status}`)}
        {campaign.remote.extension_decision.usable_delta != null
          && <> · {(100 * campaign.remote.extension_decision.usable_delta).toFixed(1)} pp</>}
      </p>}
      {campaign.result && <p>{t(`academy.remoteText.outcome.${campaign.result.outcome}`)}</p>}
      {best && <p>{t("academy.remoteText.best")} <code>{best.run_id}</code>
        {best.usable_delta != null && <> · {(100 * best.usable_delta).toFixed(1)} pp</>}</p>}
      {campaign.result?.best_qualified && <p>{t("academy.remoteText.registeredAdapter")}
        {" "}<code>{campaign.result.best_qualified.adapter_id}</code></p>}
      {campaign.qualification_status && campaign.qualification_status !== "passed" && <p role="status">
        {t(`academy.remoteText.qualification.${campaign.qualification_status}`)}
      </p>}
      {campaign.error && <p role="status">{t("academy.remoteText.syncError")}</p>}
      {campaign.status === "planned" && <Button disabled={busy} onClick={() => onAction("start")}>{t("academy.campaigns.start")}</Button>}
      {ACTIONABLE.has(campaign.status) && <Button disabled={busy || campaign.stop_requested}
        onClick={() => onAction("stop")}>{t("academy.campaigns.stop")}</Button>}
      <ul className="space-y-1">
        {Object.keys(campaign.evidence).map((runId) => (
          <li key={runId}><a className="break-all underline" href={remoteTextEvidenceUrl(campaign.campaign_id, runId)}>
            {t("academy.remoteText.evidence")} {runId}
          </a></li>
        ))}
      </ul>
    </article>
  );
}
