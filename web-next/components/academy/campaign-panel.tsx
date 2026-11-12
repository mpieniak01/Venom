"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import { listExperimentProfiles, type ExperimentProfile } from "@/lib/academy-experiments-api";
import {
  listCampaigns,
  planCampaign,
  startCampaign,
  updateCampaign,
  type Campaign,
} from "@/lib/academy-campaign-api";
import { useTranslation } from "@/lib/i18n";
import { CampaignDetail, CampaignStatus, campaignIsActive } from "./campaign-detail";
import { CampaignForm } from "./campaign-form";

const CARD = "space-y-4 rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4 sm:p-5";
const POLL_MS = 3000;
const ACTION_ERROR = {
  conflict: "academy.campaigns.conflict",
  failed: "academy.campaigns.actionError",
  optuna: "academy.campaigns.optuna.unavailable",
} as const;

export function CampaignPanel({
  onOpenRun,
  initialCampaignId,
}: {
  readonly onOpenRun: (runId: string) => void;
  readonly initialCampaignId?: string;
}) {
  const t = useTranslation();
  const [profiles, setProfiles] = useState<ExperimentProfile[] | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [profilesFailed, setProfilesFailed] = useState(false);
  const [campaignsFailed, setCampaignsFailed] = useState(false);
  const [optunaAvailable, setOptunaAvailable] = useState(false);
  const [operationError, setOperationError] = useState<keyof typeof ACTION_ERROR | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedId, setSelectedId] = useState(initialCampaignId ?? "");
  const [refresh, setRefresh] = useState(0);
  const selected = selectedId
    ? campaigns?.find((campaign) => campaign.campaign_id === selectedId)
    : campaigns?.[0];

  function refreshData() {
    setRefresh((value) => value + 1);
  }

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let inFlight = false;
    let active = false;
    const { signal } = controller;

    async function read() {
      if (signal.aborted || inFlight) return;
      clearTimeout(timer);
      inFlight = true;
      try {
        const next = await listCampaigns(signal);
        if (signal.aborted) return;
        setCampaigns(next.campaigns);
        setOptunaAvailable(next.capabilities?.optuna?.available === true);
        setCampaignsFailed(false);
        active = next.campaigns.some((campaign) => campaignIsActive(campaign.status));
      } catch {
        if (!signal.aborted) setCampaignsFailed(true);
      } finally {
        inFlight = false;
        if (!signal.aborted && active) timer = setTimeout(readVisible, POLL_MS);
      }
    }

    function readVisible() {
      if (document.visibilityState !== "hidden") void read();
    }

    void listExperimentProfiles(signal)
      .then((next) => {
        if (signal.aborted) return;
        setProfiles(next);
        setProfilesFailed(false);
      })
      .catch(() => { if (!signal.aborted) setProfilesFailed(true); });
    void read();
    document.addEventListener("visibilitychange", readVisible);
    return () => {
      controller.abort();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", readVisible);
    };
  }, [refresh]);

  async function mutate(operation: () => Promise<Campaign>) {
    if (busy) return false;
    setBusy(true);
    setOperationError(null);
    try {
      const next = await operation();
      setCampaigns((current) => [next, ...(current ?? []).filter((item) => item.campaign_id !== next.campaign_id)]);
      setSelectedId(next.campaign_id);
      refreshData();
      return true;
    } catch (error) {
      const detail = error instanceof ApiError ? (error.data as { detail?: { code?: string } } | null)?.detail : null;
      if (detail?.code === "campaign_optuna_unavailable") {
        setOptunaAvailable(false);
        setOperationError("optuna");
      } else {
        setOperationError(error instanceof ApiError && error.status === 409 ? "conflict" : "failed");
      }
      return false;
    } finally {
      setBusy(false);
    }
  }

  function act(action: "start" | "stop" | "resume") {
    if (!selected) return;
    const { campaign_id: campaignId, plan } = selected;
    if (action === "start") void mutate(() => startCampaign(campaignId, plan.plan_sha256));
    else void mutate(() => updateCampaign(campaignId, action));
  }

  const failed = profilesFailed || campaignsFailed;
  return (
    <div className="space-y-4">
      <section className={CARD}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold">{t("academy.campaigns.title")}</h3>
          <Button type="button" size="sm" variant="outline" onClick={refreshData}>{t("academy.common.refresh")}</Button>
        </div>
        {failed && <p role="alert" className="text-sm text-red-400">{t("academy.campaigns.loadError")}</p>}
        {!failed && (!profiles || !campaigns) && <p className="text-sm text-hint">{t("academy.campaigns.loading")}</p>}
        {profiles && campaigns && (
          <CampaignForm profiles={profiles} disabled={busy || failed} optunaAvailable={optunaAvailable}
            onPlan={(request) => mutate(() => planCampaign(request))} />
        )}
        {operationError && (
          <p role="alert" className="text-sm text-red-400">
            {t(ACTION_ERROR[operationError])}
          </p>
        )}
      </section>
      {campaigns && (
        <section className={CARD}>
          <h3 className="font-semibold">{t("academy.campaigns.history")}</h3>
          {campaigns.length ? (
            <ul className="space-y-2">
              {campaigns.map((item) => (
                <li key={item.campaign_id}>
                  <Button type="button" className="h-auto w-full flex-wrap justify-between text-left"
                    variant={item.campaign_id === selected?.campaign_id ? "secondary" : "outline"}
                    aria-pressed={item.campaign_id === selected?.campaign_id}
                    onClick={() => setSelectedId(item.campaign_id)}>
                    <span className="break-all">{item.campaign_id}</span>
                    <span className="text-xs text-hint"><CampaignStatus status={item.status} /></span>
                  </Button>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-hint">{t("academy.campaigns.noCampaigns")}</p>}
        </section>
      )}
      {campaigns && selectedId && !selected && (
        <output>{t("academy.campaigns.campaignUnavailable")} <code>{selectedId}</code></output>
      )}
      {selected && <section className={CARD}>
        <CampaignDetail key={selected.campaign_id} campaign={selected} disabled={busy || campaignsFailed} optunaAvailable={optunaAvailable}
          onAction={act} onOpenRun={onOpenRun} onChanged={refreshData} />
      </section>}
    </div>
  );
}
