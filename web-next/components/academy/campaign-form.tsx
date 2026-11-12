"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CampaignRequest, CampaignStrategy, OptunaSearchSpace } from "@/lib/academy-campaign-api";
import type { ExperimentProfile, ExperimentRecipe } from "@/lib/academy-experiments-api";
import { useTranslation } from "@/lib/i18n";
import type { QualityCampaignDraft } from "@/lib/academy-quality-api";
import { CampaignPolicyFields, PinnedQualitySource, readQualityPolicy } from "./campaign-quality-policy";
import { OPTUNA_PARAMETERS, OptunaFields } from "./campaign-optuna";

const MIB = 1024 ** 2;
const DRAFT_RECIPE_FIELDS = new Set([
  "rank", "alpha", "dropout", "target_modules", "steps", "save_every", "warmup_steps", "learning_rate",
  "max_tokens", "microbatch", "gradient_accumulation_steps", "seed", "lr_scheduler_type",
  "train_sha256", "max_supervised_tokens",
]);
const LANGUAGE_TARGET_MODULES = new Set([
  "q_proj", "k_proj", "v_proj", "o_proj", "in_proj", "out_proj", "w1", "w2", "w3",
]);

function unsupportedDraftFields(recipe: Record<string, unknown>) {
  const fields = Object.keys(recipe).filter((key) => !DRAFT_RECIPE_FIELDS.has(key));
  const modules = recipe.target_modules;
  if (modules !== undefined && (!Array.isArray(modules)
    || !modules.length || modules.some((item) => typeof item !== "string" || !LANGUAGE_TARGET_MODULES.has(item)))) {
    fields.push("target_modules");
  }
  return fields;
}

function draftTokenBudget(draft: QualityCampaignDraft | undefined) {
  return draft?.variants.reduce((total, { recipe }) => {
    const { steps, max_tokens, microbatch, gradient_accumulation_steps, max_supervised_tokens } = recipe;
    if (typeof steps !== "number" || typeof max_tokens !== "number"
      || typeof microbatch !== "number" || typeof gradient_accumulation_steps !== "number") return total;
    const bound = steps * max_tokens * microbatch * gradient_accumulation_steps;
    const reserved = typeof max_supervised_tokens === "number" ? Math.min(bound, max_supervised_tokens) : bound;
    return total + reserved;
  }, 0) ?? 0;
}

const BUDGET_FIELDS = [
  ["max_trials", 3, 1, 32],
  ["max_updates", 1000, 1, 100000],
  ["max_tokens", 2000000, 1, 1000000000],
  ["max_seconds", 3600, 1, 604800],
  ["trial_seconds", 1200, 1, 86400],
  ["max_retries", 0, 0, 3],
  ["max_artifact_mib", 4096, 1, 1048576],
  ["min_free_mib", 8192, 0, 1048576],
] as const;
const VARIANT_FIELDS = [
  ["rank", "academy.experiments.rank"],
  ["alpha", "academy.experiments.alpha"],
  ["learning_rate", "academy.experiments.learningRate"],
] as const;
const SELECT_CLASS = "h-9 w-full rounded-md border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-2 text-sm";

function numberField(data: FormData, name: string) {
  const value = data.get(name);
  if (typeof value !== "string" || !value.trim() || !Number.isFinite(Number(value))) {
    throw new Error("invalid numeric field");
  }
  return Number(value);
}

function variantRecipe(data: FormData, row: number, editableRecipe: boolean): Record<string, unknown> {
  if (editableRecipe) {
    const json = data.get("variant-json-" + row);
    if (typeof json !== "string") throw new Error("draft recipe must be text");
    const recipe: unknown = JSON.parse(json);
    if (!recipe || typeof recipe !== "object" || Array.isArray(recipe)
      || unsupportedDraftFields(recipe as Record<string, unknown>).length) {
      throw new Error("invalid draft recipe");
    }
    return recipe as Record<string, unknown>;
  }
  const recipe: ExperimentRecipe = {};
  for (const [key] of VARIANT_FIELDS) {
    const name = `variant-${row}-${key}`;
    if (data.get(name) !== "") recipe[key] = numberField(data, name);
  }
  return { ...recipe };
}

function readOptunaPlan(data: FormData): Pick<CampaignRequest, "variants" | "strategy" | "search_space" | "sampler_seed"> {
  const searchSpace: OptunaSearchSpace = {};
  for (const { key, min, max, integer } of OPTUNA_PARAMETERS) {
    if (!data.has("optuna-" + key + "-enabled")) continue;
    const low = numberField(data, "optuna-" + key + "-low");
    const high = numberField(data, "optuna-" + key + "-high");
    const log = data.has("optuna-" + key + "-log");
    if (low < min || high > max || low >= high
      || (integer && !(Number.isInteger(low) && Number.isInteger(high))) || (log && low <= 0)) {
      throw new Error("invalid Optuna range");
    }
    searchSpace[key] = { low, high, log };
  }
  const seed = numberField(data, "sampler_seed");
  if (!Object.keys(searchSpace).length || !Number.isInteger(seed) || seed < 0 || seed > 2 ** 32 - 1) {
    throw new Error("invalid Optuna search space or seed");
  }
  return { strategy: "optuna", variants: [], search_space: searchSpace, sampler_seed: seed };
}

function readPlan(
  data: FormData, profileId: string, rows: number[], strategy: CampaignStrategy, draft?: QualityCampaignDraft,
): CampaignRequest {
  const campaignId = data.get("campaign_id");
  if (typeof campaignId !== "string") throw new Error("campaign id must be text");
  const id = campaignId.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$/.test(id)) throw new Error("invalid campaign id");
  const qualityPolicy = readQualityPolicy(data, draft?.qualityPolicy.source_record_id);
  return {
    campaign_id: id,
    profile_id: profileId,
    ...(strategy === "optuna"
      ? readOptunaPlan(data)
      : { variants: rows.map((row) => variantRecipe(data, row, Boolean(draft))) }),
    ...(qualityPolicy ? { quality_policy: qualityPolicy } : {}),
    budget: {
      max_trials: numberField(data, "max_trials"),
      max_updates: numberField(data, "max_updates"),
      max_tokens: numberField(data, "max_tokens"),
      max_seconds: numberField(data, "max_seconds"),
      trial_seconds: numberField(data, "trial_seconds"),
      max_retries: numberField(data, "max_retries"),
      max_artifact_bytes: numberField(data, "max_artifact_mib") * MIB,
      min_free_bytes: numberField(data, "min_free_mib") * MIB,
    },
    selection: {
      min_usable_delta: numberField(data, "min_usable_delta") / 100,
      max_critical_delta: numberField(data, "max_critical_delta") / 100,
    },
    retention: data.get("retention") === "discard_rejected" ? "discard_rejected" : "keep_all",
    review_mode: data.get("review_mode") === "automatic" ? "automatic" : "manual",
  };
}

interface CampaignFormProps {
  readonly profiles: ExperimentProfile[];
  readonly disabled: boolean;
  readonly optunaAvailable: boolean;
  readonly draft?: QualityCampaignDraft;
  readonly onDiscardDraft: () => void;
  readonly onPlan: (request: CampaignRequest) => Promise<boolean>;
}

export function CampaignForm({ profiles, disabled, optunaAvailable, draft, onDiscardDraft, onPlan }: CampaignFormProps) {
  const t = useTranslation();
  const [profileId, setProfileId] = useState(draft?.profileId ?? "");
  const [rows, setRows] = useState(() => draft?.variants.map((_, index) => index) ?? [0]);
  const [strategy, setStrategy] = useState<CampaignStrategy>("fixed");
  const unavailableStrategy = strategy === "optuna" && !optunaAvailable;
  const invalidMessage = strategy === "optuna" ? "academy.campaigns.optuna.invalid" : "academy.campaigns.invalid";
  const [invalid, setInvalid] = useState(false);
  const profile = profiles.find((item) => item.id === profileId) ?? (draft ? undefined : profiles[0]);
  const unsupportedFields = [...new Set(draft?.variants.flatMap((variant) =>
    unsupportedDraftFields(variant.recipe)) ?? [])];
  if (!profiles.length) return <p className="text-sm text-hint">{t("academy.experiments.noProfiles")}</p>;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled || !profile || unavailableStrategy) return;
    try {
      const request = readPlan(new FormData(event.currentTarget), profile.id, rows, strategy, draft);
      if (request.variants.length > request.budget.max_trials || request.budget.trial_seconds > request.budget.max_seconds) {
        setInvalid(true);
        return;
      }
      setInvalid(false);
      await onPlan(request);
    } catch {
      setInvalid(true);
    }
  }

  return (
    <form className="space-y-4" onSubmit={(event) => void submit(event)}>
      {draft && (
        <div className="space-y-2 rounded-lg border border-[color:var(--ui-border)] p-3">
          <output className="block text-sm text-hint">{t("academy.campaigns.quality.draftReady")}</output>
          <PinnedQualitySource recordId={draft.qualityPolicy.source_record_id} fixed={draft.fixed} />
          <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={onDiscardDraft}>
            {t("academy.campaigns.quality.discardDraft")}
          </Button>
        </div>
      )}
      {unsupportedFields.length > 0 && (
        <p className="break-all text-sm text-hint">
          {t("academy.campaigns.quality.unsupportedFields")} <code>{unsupportedFields.join(", ")}</code>
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="campaign-profile">{t("academy.experiments.profile")}</Label>
          <select id="campaign-profile" className={SELECT_CLASS} value={profile?.id ?? ""} disabled={disabled} required
            onChange={(event) => setProfileId(event.currentTarget.value)}>
            {draft && <option value="">{t("academy.campaigns.quality.selectProfile")}</option>}
            {profiles.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="campaign-id">{t("academy.campaigns.id")}</Label>
          <Input id="campaign-id" name="campaign_id" required maxLength={40} disabled={disabled} />
        </div>
      </div>
      {profile && <p className="break-words text-sm text-hint">{profile.model} · {profile.dataset}</p>}
      <div className="space-y-1 sm:max-w-xs">
        <Label htmlFor="campaign-strategy">{t("academy.campaigns.strategy")}</Label>
        <select id="campaign-strategy" className={SELECT_CLASS} value={strategy} disabled={disabled}
          aria-describedby={!optunaAvailable ? "campaign-optuna-unavailable" : undefined}
          onChange={(event) => {
            setStrategy(event.currentTarget.value === "optuna" ? "optuna" : "fixed");
            setInvalid(false);
          }}>
          <option value="fixed">{t("academy.campaigns.fixed")}</option>
          <option value="optuna" disabled={!optunaAvailable}>{t("academy.campaigns.optuna.name")}</option>
        </select>
        {!optunaAvailable && (
          <p id="campaign-optuna-unavailable" className="text-sm text-hint">{t("academy.campaigns.optuna.unavailable")}</p>
        )}
      </div>
      {strategy === "optuna" && <OptunaFields disabled={disabled || unavailableStrategy} />}
      <fieldset className="space-y-3" hidden={strategy !== "fixed"} disabled={strategy !== "fixed"}>
        <legend className="text-sm font-medium">{t("academy.campaigns.variants")}</legend>
        {rows.map((row, index) => (
          <div key={row} className="space-y-2 rounded-lg border border-[color:var(--ui-border)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm text-hint">{t("academy.campaigns.variant")} {index + 1}</span>
              <Button type="button" size="sm" variant="ghost" disabled={disabled || rows.length <= 1}
                onClick={() => setRows((current) => current.filter((item) => item !== row))}>
                {t("academy.campaigns.removeVariant")}
              </Button>
            </div>
            {draft ? (
              <div className="space-y-1">
                <Label htmlFor={`variant-json-${row}`}>
                  {t("academy.campaigns.quality.recipeJson")} {index + 1}
                </Label>
                <textarea id={`variant-json-${row}`} name={`variant-json-${row}`} rows={8}
                  className="w-full rounded-md border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-2 font-mono text-xs"
                  defaultValue={JSON.stringify(draft.variants[row]?.recipe ?? {}, null, 2)} required disabled={disabled} />
              </div>
            ) : <div className="grid gap-2 sm:grid-cols-3">
              {VARIANT_FIELDS.map(([field, label]) => (
                <div className="space-y-1" key={field}>
                  <Label htmlFor={`variant-${row}-${field}`}>{t(label)}</Label>
                  <Input id={`variant-${row}-${field}`} name={`variant-${row}-${field}`} type="number"
                    min={field === "learning_rate" ? undefined : 1}
                    step={field === "learning_rate" ? "any" : 1}
                    placeholder={profile?.recipe[field]?.toString()} disabled={disabled} />
                </div>
              ))}
            </div>}
          </div>
        ))}
        <Button type="button" size="sm" variant="outline" disabled={disabled || rows.length >= 32}
          onClick={() => setRows((current) => [...current, Math.max(current.at(-1) ?? 0, (draft?.variants.length ?? 1) - 1) + 1])}>
          {t("academy.campaigns.addVariant")}
        </Button>
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="campaign-retention">{t("academy.campaigns.retention")}</Label>
          <select id="campaign-retention" name="retention" className={SELECT_CLASS} disabled={disabled}>
            <option value="keep_all">{t("academy.campaigns.keepAll")}</option>
            <option value="discard_rejected">{t("academy.campaigns.discardRejected")}</option>
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="campaign-review">{t("academy.campaigns.reviewMode")}</Label>
          <select id="campaign-review" name="review_mode" className={SELECT_CLASS} disabled={disabled}>
            <option value="manual">{t("academy.campaigns.manualReview")}</option>
            <option value="automatic" disabled={!profile?.automatic_review}>{t("academy.campaigns.automaticReview")}</option>
          </select>
        </div>
      </div>
      <CampaignPolicyFields disabled={disabled} initial={draft?.qualityPolicy} />
      <details open>
        <summary className="cursor-pointer text-sm font-medium">{t("academy.campaigns.limits")}</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {BUDGET_FIELDS.map(([field, initial, min, max]) => (
            <div className="space-y-1" key={field}>
              <Label htmlFor={`campaign-${field}`}>{t(`academy.campaigns.budget.${field}`)}</Label>
              <Input id={`campaign-${field}`} name={field} type="number" step={1} min={min} max={max}
                defaultValue={field === "max_tokens" ? Math.max(initial, draftTokenBudget(draft)) : initial} required disabled={disabled} />
            </div>
          ))}
          <div className="space-y-1">
            <Label htmlFor="campaign-min-usable">{t("academy.campaigns.minUsable")}</Label>
            <Input id="campaign-min-usable" name="min_usable_delta" type="number" min={-100} max={100} step="any"
              defaultValue={0} required disabled={disabled} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="campaign-max-critical">{t("academy.campaigns.maxCritical")}</Label>
            <Input id="campaign-max-critical" name="max_critical_delta" type="number" min={0} max={100} step="any"
              defaultValue={0} required disabled={disabled} />
          </div>
        </div>
      </details>
      {invalid && <p role="alert" className="text-sm text-red-400">
        {t(draft ? "academy.campaigns.quality.invalidDraft" : invalidMessage)}
      </p>}
      <Button type="submit" disabled={disabled || unavailableStrategy || !profile}>{t("academy.campaigns.plan")}</Button>
    </form>
  );
}
