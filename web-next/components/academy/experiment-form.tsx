"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useTranslation } from "@/lib/i18n";
import type { ExperimentProfile, ExperimentRecipe, ExperimentStartRequest } from "@/lib/academy-experiments-api";

import { DataAuditSummary } from "./data-audit-summary";

const RECIPE_FIELDS = ["rank", "alpha", "learning_rate"] as const;
const FIELD_KEYS = {
  rank: "academy.experiments.rank",
  alpha: "academy.experiments.alpha",
  learning_rate: "academy.experiments.learningRate",
} as const;

function readRecipe(data: FormData, defaults: ExperimentRecipe): ExperimentRecipe {
  const recipe: ExperimentRecipe = {};
  for (const field of RECIPE_FIELDS) {
    const raw = data.get(field);
    if (typeof raw !== "string" || !raw) continue;
    const value = Number(raw);
    if (!Number.isFinite(value) || value <= 0 || (field !== "learning_rate" && !Number.isInteger(value))) {
      throw new Error("invalid recipe");
    }
    if (value !== defaults[field]) recipe[field] = value;
  }
  return recipe;
}

interface ExperimentFormProps {
  readonly profiles: ExperimentProfile[];
  readonly disabled: boolean;
  readonly onStart: (request: ExperimentStartRequest) => Promise<boolean>;
}

export function ExperimentForm({ profiles, disabled, onStart }: ExperimentFormProps) {
  const t = useTranslation();
  const [profileId, setProfileId] = useState("");
  const [runId, setRunId] = useState("");
  const [invalid, setInvalid] = useState(false);
  const profile = profiles.find((item) => item.id === profileId) ?? profiles[0];

  const auditBlocked = profile?.data_audit?.status === "blocked";

  if (!profile) return <p className="text-sm text-hint">{t("academy.experiments.noProfiles")}</p>;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled || auditBlocked) return;
    let recipe: ExperimentRecipe;
    const id = runId.trim();
    try {
      if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(id)) throw new Error("invalid run id");
      recipe = readRecipe(new FormData(event.currentTarget), profile.recipe);
    } catch {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    const started = await onStart({ profile_id: profile.id, run_id: id, recipe });
    if (started) setRunId("");
  }

  return (
    <form className="space-y-4" onSubmit={(event) => void submit(event)}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="experiment-profile">{t("academy.experiments.profile")}</Label>
          <select
            id="experiment-profile"
            className="h-9 w-full rounded-md border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-2 text-sm"
            value={profile.id}
            disabled={disabled}
            onChange={(event) => setProfileId(event.currentTarget.value)}
          >
            {profiles.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="experiment-run-id">{t("academy.experiments.runId")}</Label>
          <Input
            id="experiment-run-id"
            required
            maxLength={64}
            value={runId}
            disabled={disabled}
            onChange={(event) => setRunId(event.currentTarget.value)}
          />
        </div>
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <div className="min-w-0">
          <dt className="text-hint">{t("academy.experiments.model")}</dt>
          <dd className="break-words">{profile.model}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-hint">{t("academy.experiments.dataset")}</dt>
          <dd className="break-words">{profile.dataset}</dd>
        </div>
      </dl>
      <DataAuditSummary audit={profile.data_audit} />
      <details>
        <summary className="cursor-pointer text-sm font-medium">{t("academy.experiments.recipe")}</summary>
        <div key={profile.id} className="mt-3 grid gap-3 sm:grid-cols-3">
          {RECIPE_FIELDS.map((field) => (
            <div className="space-y-1" key={field}>
              <Label htmlFor={`experiment-recipe-${field}`}>{t(FIELD_KEYS[field])}</Label>
              <Input
                id={`experiment-recipe-${field}`}
                name={field}
                type="number"
                min={field === "learning_rate" ? undefined : 1}
                step={field === "learning_rate" ? "any" : 1}
                defaultValue={profile.recipe[field]}
                disabled={disabled}
              />
            </div>
          ))}
        </div>
      </details>
      {invalid && <p role="alert" className="text-sm text-red-400">{t("academy.experiments.invalidRecipe")}</p>}
      <Button type="submit" disabled={disabled || auditBlocked}>{t("academy.experiments.start")}</Button>
    </form>
  );
}
