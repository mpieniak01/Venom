"use client";

import type { Campaign, CampaignFinalInputs, CampaignFinalQualification } from "@/lib/academy-campaign-api";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { useLanguage, useTranslation } from "@/lib/i18n";

const PREFIX = "academy.campaigns.finalQualification.";
const QUALIFICATION_STATES = new Set(["pending", "running", "passed", "failed_quality", "incomplete"]);

export function readFinalQualification(data: FormData, inputs: CampaignFinalInputs[]): CampaignFinalQualification | undefined {
  const inputsId = data.get("final_inputs_id");
  if (!inputsId) return undefined;
  const reserve = Number(data.get("final_reserve_seconds"));
  const registered = inputs.find((item) => item.inputs_id === inputsId);
  const total = Number(data.get("max_seconds"));
  if (!registered || !Number.isSafeInteger(reserve) || reserve < 1
    || reserve >= total || reserve < registered.max_seconds) {
    throw new Error("invalid final qualification reserve");
  }
  return { inputs_id: registered.inputs_id, reserve_seconds: reserve };
}

export function CampaignFinalFields({ inputs, failed, disabled, automaticReview }: {
  readonly inputs: CampaignFinalInputs[];
  readonly failed: boolean;
  readonly disabled: boolean;
  readonly automaticReview: boolean;
}) {
  const t = useTranslation();
  return (
    <fieldset className="space-y-2 rounded-lg border border-[color:var(--ui-border)] p-3" disabled={disabled || !automaticReview}>
      <legend className="text-sm font-medium">{t(PREFIX + "title")}</legend>
      <p className="text-sm text-hint">{t(PREFIX + "hint")}</p>
      {failed && <p role="alert" className="text-sm text-red-400">{t(PREFIX + "loadError")}</p>}
      {!failed && !inputs.length && <p className="text-sm text-hint">{t(PREFIX + "noInputs")}</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="campaign-final-inputs">{t(PREFIX + "inputs")}</Label>
          <select id="campaign-final-inputs" name="final_inputs_id" defaultValue="" disabled={failed || !inputs.length}
            className="h-9 w-full rounded-md border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-2 text-sm">
            <option value="">{t(PREFIX + "none")}</option>
            {inputs.map((item) => <option key={item.inputs_id} value={item.inputs_id}>{item.inputs_id}</option>)}
          </select>
          <p className="text-sm text-hint">{t(PREFIX + "automatic")}</p>
        </div>
        <div className="space-y-1">
          <Label htmlFor="campaign-final-reserve">{t(PREFIX + "reserve")}</Label>
          <Input id="campaign-final-reserve" name="final_reserve_seconds" type="number" min={1} step={1} defaultValue={900} />
        </div>
      </div>
    </fieldset>
  );
}

export function CampaignFinalSummary({ campaign }: { readonly campaign: Campaign }) {
  const { t, language } = useLanguage();
  const plan = campaign.plan.final_qualification;
  if (!plan) return null;
  const status = campaign.qualification_status ?? "pending";
  const statusKey = QUALIFICATION_STATES.has(status) ? status : "unverified";
  const deadline = campaign.deadline_at;
  const delta = campaign.qualification?.usable_delta;
  const format = new Intl.NumberFormat(language, { maximumFractionDigits: 2, signDisplay: "exceptZero" });
  return (
    <section aria-label={t(PREFIX + "title")} className="space-y-2 rounded-lg border border-[color:var(--ui-border)] p-3">
      <h4 className="font-medium">{t(PREFIX + "title")}</h4>
      <p role="status" className="font-medium">{t(PREFIX + statusKey)}</p>
      <dl className="flex flex-wrap gap-4 text-sm">
        <div><dt className="text-hint">{t(PREFIX + "inputs")}</dt><dd>{plan.inputs_id}</dd></div>
        <div><dt className="text-hint">{t(PREFIX + "reserve")}</dt><dd>{plan.reserve_seconds}</dd></div>
        {typeof deadline === "number" && Number.isFinite(deadline) && (
          <div><dt className="text-hint">{t(PREFIX + "deadline")}</dt>
            <dd>{new Date(deadline * 1000).toLocaleString(language)}</dd></div>
        )}
      </dl>
      {typeof delta === "number" && Number.isFinite(delta) && (
        <p className="text-sm">{t("academy.campaigns.quality.policy.parentDelta")} · {format.format(delta * 100)} {t("academy.campaigns.quality.guard.points")}</p>
      )}
      <p className="text-sm text-hint">{t(PREFIX + "scope")}</p>
    </section>
  );
}
