"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLanguage, useTranslation } from "@/lib/i18n";
import type { CampaignPlan, OptunaParameter } from "@/lib/academy-campaign-api";

export const OPTUNA_PARAMETERS = [
  { key: "rank", label: "academy.experiments.rank", min: 1, max: 64, integer: true },
  { key: "alpha", label: "academy.experiments.alpha", min: 1, max: 256, integer: true },
  { key: "learning_rate", label: "academy.experiments.learningRate", min: 1e-7, max: 0.01, integer: false },
  { key: "dropout", label: "academy.campaigns.optuna.dropout", min: 0, max: 0.5, integer: false },
] as const satisfies ReadonlyArray<{
  key: OptunaParameter;
  label: string;
  min: number;
  max: number;
  integer: boolean;
}>;

export function OptunaFields({ disabled }: { readonly disabled: boolean }) {
  const t = useTranslation();
  const [active, setActive] = useState<Partial<Record<OptunaParameter, boolean>>>({ learning_rate: true });

  return (
    <fieldset className="space-y-3" disabled={disabled}>
      <legend className="text-sm font-medium">{t("academy.campaigns.optuna.space")}</legend>
      <p className="text-sm text-hint">{t("academy.campaigns.optuna.spaceHint")}</p>
      {OPTUNA_PARAMETERS.map(({ key, label, min, max, integer }) => {
        const name = `optuna-${key}`;
        const enabled = active[key] ?? false;
        return (
          <div key={key} className="space-y-2 rounded-lg border border-[color:var(--ui-border)] p-3">
            <Label htmlFor={name + "-enabled"} className="flex items-center gap-2">
              <input
                id={name + "-enabled"}
                type="checkbox"
                name={`${name}-enabled`}
                checked={enabled}
                onChange={(event) => setActive({ ...active, [key]: event.currentTarget.checked })}
              />
              {t(label)}
            </Label>
            {enabled && (
              <div className="grid gap-2 sm:grid-cols-3">
                <div className="space-y-1">
                  <Label htmlFor={`${name}-low`}>{t(label)} · {t("academy.campaigns.optuna.low")}</Label>
                  <Input id={`${name}-low`} name={`${name}-low`} type="number" min={min} max={max}
                    step={integer ? 1 : "any"} required />
                </div>
                <div className="space-y-1">
                  <Label htmlFor={`${name}-high`}>{t(label)} · {t("academy.campaigns.optuna.high")}</Label>
                  <Input id={`${name}-high`} name={`${name}-high`} type="number" min={min} max={max}
                    step={integer ? 1 : "any"} required />
                </div>
                <Label htmlFor={name + "-log"} className="flex items-center gap-2 self-end py-2">
                  <input id={name + "-log"} type="checkbox" name={`${name}-log`} defaultChecked={key === "learning_rate"} />
                  {t("academy.campaigns.optuna.logarithmic")}
                </Label>
              </div>
            )}
          </div>
        );
      })}
      <div className="space-y-1 sm:max-w-xs">
        <Label htmlFor="optuna-seed">{t("academy.campaigns.optuna.seed")}</Label>
        <Input id="optuna-seed" name="sampler_seed" type="number" min={0} max={2 ** 32 - 1}
          step={1} defaultValue={42} required />
      </div>
    </fieldset>
  );
}

export function OptunaPlanSummary({ plan }: { readonly plan: CampaignPlan }) {
  const { t, language } = useLanguage();
  const display = new Intl.NumberFormat(language, { maximumSignificantDigits: 12 });

  return (
    <section className="space-y-2 rounded-lg border border-[color:var(--ui-border)] p-3">
      <h4 className="font-medium">{t("academy.campaigns.optuna.approvedSpace")}</h4>
      <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {OPTUNA_PARAMETERS.map(({ key, label }) => {
          const range = plan.search_space?.[key];
          if (!range) return null;
          return (
            <div key={key}>
              <dt className="text-hint">{t(label)}</dt>
              <dd>
                {display.format(range.low)} – {display.format(range.high)} · {t(range.log
                  ? "academy.campaigns.optuna.logarithmic" : "academy.campaigns.optuna.linear")}
              </dd>
            </div>
          );
        })}
        {typeof plan.sampler_seed === "number" && (
          <div>
            <dt className="text-hint">{t("academy.campaigns.optuna.seed")}</dt>
            <dd>{plan.sampler_seed}</dd>
          </div>
        )}
      </dl>
    </section>
  );
}
