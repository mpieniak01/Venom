"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLanguage, useTranslation } from "@/lib/i18n";
import { listQualityRecords, type CampaignQualityPolicy, type TrialQualityGuard } from "@/lib/academy-quality-api";

const QUALITY = "academy.campaigns.quality.";
const TEXTAREA = "w-full rounded-md border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-3 py-2 text-sm";

function textValue(value: FormDataEntryValue | null | undefined): string {
  if (value == null) return "";
  if (typeof value !== "string") throw new Error("quality policy field must be text");
  return value.trim();
}

export function readQualityPolicy(data: FormData, sourceRecordId?: string): CampaignQualityPolicy | undefined {
  if (!sourceRecordId && !data.has("quality-policy-enabled")) return undefined;
  const categories = data.getAll("quality-category").map(textValue);
  const thresholds = data.getAll("quality-minimum");
  if (new Set(categories).size !== categories.length || categories.length !== thresholds.length) {
    throw new Error("invalid quality category thresholds");
  }
  const deltas = categories.map((category, index) => {
    const raw = textValue(thresholds[index]);
    const value = Number(raw);
    if (!category || !raw || !Number.isFinite(value) || value < -100 || value > 100) {
      throw new Error("invalid quality category minimum");
    }
    return [category, value / 100] as const;
  });
  const references = data.getAll("quality-reference-record-id").map(textValue);
  const protectedIds = [...new Set(textValue(data.get("quality-protected-cases")).split(/\r?\n/)
    .map((line) => line.trim()).filter(Boolean))];
  if (references.length > 8 || protectedIds.length > 2048 || deltas.length > 64) {
    throw new Error("quality policy exceeds its limits");
  }
  const hypothesis = textValue(data.get("quality-hypothesis"));
  return {
    ...(hypothesis ? { hypothesis } : {}),
    ...(sourceRecordId ? { source_record_id: sourceRecordId } : {}),
    reference_record_ids: references,
    protected_case_ids: protectedIds,
    protect_reference_hits: data.has("quality-protect-reference-hits"),
    protect_base_hits: data.has("quality-protect-base-hits"),
    no_new_critical: data.has("quality-no-new-critical"),
    min_category_usable_delta: Object.fromEntries(deltas),
  };
}

function PolicyReferences({ initial }: { readonly initial?: CampaignQualityPolicy }) {
  const t = useTranslation();
  const [recordIds, setRecordIds] = useState<string[] | null>(null);
  const [error, setError] = useState(false);
  const initialIds = initial?.reference_record_ids ?? [];
  const options = [...new Set([...(recordIds ?? []), ...initialIds])];

  useEffect(() => {
    const controller = new AbortController();
    void listQualityRecords(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setRecordIds(items.filter((item) => item.split === "dev").map((item) => item.record_id));
      })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, []);

  return (
    <fieldset className="space-y-1">
      <legend className="text-sm font-medium">{t(QUALITY + "policy.references")}</legend>
      {error && <p role="alert" className="text-sm text-red-400">{t(QUALITY + "historyError")}</p>}
      {!error && !recordIds && <p className="text-sm text-hint">{t(QUALITY + "loading")}</p>}
      {!error && recordIds && !options.length && <p className="text-sm text-hint">{t(QUALITY + "policy.noReferences")}</p>}
      <div className="max-h-40 space-y-1 overflow-auto">
        {options.map((id) => (
          <Label htmlFor={`quality-policy-ref-${id}`} className="flex items-center gap-2 break-all" key={id}>
            <input id={`quality-policy-ref-${id}`} name="quality-reference-record-id" type="checkbox"
              value={id} defaultChecked={initialIds.includes(id)} />
            {id}
          </Label>
        ))}
      </div>
    </fieldset>
  );
}

export function CampaignPolicyFields({ disabled, initial }: {
  readonly disabled: boolean;
  readonly initial?: CampaignQualityPolicy;
}) {
  const t = useTranslation();
  const sourceLocked = Boolean(initial?.source_record_id);
  const [operatorEnabled, setEnabled] = useState(Boolean(initial));
  const enabled = sourceLocked || operatorEnabled;
  const [mounted, setMounted] = useState(Boolean(initial));

  function changeEnabled(checked: boolean) {
    setEnabled(checked);
    if (checked) setMounted(true);
  }
  const defaults = Object.entries(initial?.min_category_usable_delta ?? {});
  const [rows, setRows] = useState(() => defaults.map((_, index) => index));

  return (
    <details open={initial ? true : undefined} className="space-y-2">
      <summary className="cursor-pointer text-sm font-medium">{t(QUALITY + "policy.title")}</summary>
      <Label htmlFor="quality-policy-enabled" className="flex items-center gap-2">
        <input id="quality-policy-enabled" name="quality-policy-enabled" type="checkbox" checked={enabled}
          disabled={disabled || sourceLocked} onChange={(event) => changeEnabled(event.currentTarget.checked)} />
        {t(QUALITY + "policy.enable")}
      </Label>
      {sourceLocked && <p className="text-xs text-hint">{t(QUALITY + "policy.sourceLocked")}</p>}
      {mounted && (
        <fieldset hidden={!enabled} disabled={disabled || !enabled} className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="quality-hypothesis">{t(QUALITY + "hypothesis")}</Label>
            <textarea className={TEXTAREA} id="quality-hypothesis" name="quality-hypothesis" rows={2}
              maxLength={1000} defaultValue={initial?.hypothesis ?? undefined} />
          </div>
          <PolicyReferences initial={initial} />
          <div className="space-y-1">
            <Label htmlFor="quality-protected-cases">{t(QUALITY + "policy.protectedIds")}</Label>
            <textarea className={TEXTAREA} id="quality-protected-cases" name="quality-protected-cases" rows={3}
              aria-describedby="quality-protected-hint" defaultValue={initial?.protected_case_ids.join("\n")} />
            <p id="quality-protected-hint" className="text-xs text-hint">{t(QUALITY + "policy.protectedHint")}</p>
          </div>
          <div className="flex flex-wrap gap-3">
            {([
              ["protect-reference-hits", initial?.protect_reference_hits ?? true, "protectReference"],
              ["protect-base-hits", initial?.protect_base_hits ?? false, "protectBase"],
              ["no-new-critical", initial?.no_new_critical ?? true, "noNewCritical"],
            ] as const).map(([key, checked, label]) => (
              <Label htmlFor={`quality-${key}`} key={key} className="flex items-center gap-2">
                <input id={`quality-${key}`} name={`quality-${key}`} type="checkbox" defaultChecked={checked} />
                {t(QUALITY + "policy." + label)}
              </Label>
            ))}
          </div>
          {rows.map((row) => (
            <div key={row} className="grid items-end gap-2 sm:grid-cols-[1fr_1fr_auto]">
              <div className="space-y-1">
                <Label htmlFor={`quality-category-${row}`}>{t(QUALITY + "category")}</Label>
                <Input id={`quality-category-${row}`} name="quality-category" defaultValue={defaults[row]?.[0]}
                  required maxLength={80} />
              </div>
              <div className="space-y-1">
                <Label htmlFor={`quality-minimum-${row}`}>{t(QUALITY + "policy.minimum")}</Label>
                <Input id={`quality-minimum-${row}`} name="quality-minimum" type="number" step="any" min={-100} max={100}
                  defaultValue={defaults[row] ? defaults[row][1] * 100 : 0} required />
              </div>
              <Button type="button" variant="ghost" size="sm" onClick={() => setRows((current) => current.filter((id) => id !== row))}>
                {t(QUALITY + "policy.removeMinimum")}
              </Button>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" disabled={rows.length >= 64}
            onClick={() => setRows((current) => [...current, (current.at(-1) ?? -1) + 1])}>
            {t(QUALITY + "policy.addMinimum")}
          </Button>
        </fieldset>
      )}
    </details>
  );
}

export function PinnedQualitySource({ recordId, fixed }: {
  readonly recordId: string;
  readonly fixed?: { train_sha256: string | null; runtime: Record<string, unknown> | null };
}) {
  const t = useTranslation();

  return (
    <div className="space-y-1 text-sm">
      <dl>
        <div><dt className="text-hint">{t(QUALITY + "sourceRecord")}</dt><dd className="break-all"><code>{recordId}</code></dd></div>
        {fixed?.train_sha256 && (
          <div><dt className="text-hint">{t(QUALITY + "trainingHash")}</dt><dd className="break-all"><code>{fixed.train_sha256}</code></dd></div>
        )}
      </dl>
      {fixed?.runtime && (
        <details>
          <summary className="cursor-pointer text-hint">{t(QUALITY + "runtime")}</summary>
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(fixed.runtime, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}

export function QualityPolicySummary({ policy }: { readonly policy: CampaignQualityPolicy }) {
  const { t, language } = useLanguage();
  const format = new Intl.NumberFormat(language, { maximumFractionDigits: 2 });
  const minima = Object.entries(policy.min_category_usable_delta);
  const protection = [
    [policy.protect_reference_hits, "protectReference"],
    [policy.protect_base_hits, "protectBase"],
    [policy.no_new_critical, "noNewCritical"],
  ] as const;

  return (
    <section className="space-y-2 rounded-lg border border-[color:var(--ui-border)] p-3 text-sm">
      <h4 className="font-medium">{t(QUALITY + "policy.title")}</h4>
      {policy.source_record_id && <PinnedQualitySource recordId={policy.source_record_id} fixed={policy.source_record} />}
      {policy.hypothesis && (
        <dl>
          <dt className="text-hint">{t(QUALITY + "hypothesis")}</dt>
          <dd className="whitespace-pre-wrap break-words">{policy.hypothesis}</dd>
        </dl>
      )}
      <ul className="space-y-1">
        {protection.map(([enabled, label]) => enabled && <li key={label}>{t(QUALITY + "policy." + label)}</li>)}
        <li>{t(QUALITY + "policy.protectedIds")} · {policy.protected_case_ids.length}</li>
        {minima.map(([category, minimum]) => (
          <li key={category}>{category} · {t(QUALITY + "policy.minimum")} {format.format(minimum * 100)}</li>
        ))}
      </ul>
      {policy.reference_record_ids.length > 0 && (
        <p className="break-all">{t(QUALITY + "policy.references")} · {policy.reference_record_ids.join(", ")}</p>
      )}
    </section>
  );
}

export function TrialQualityDecision({ guard }: { readonly guard: TrialQualityGuard }) {
  const { t, language } = useLanguage();
  const format = new Intl.NumberFormat(language, { maximumFractionDigits: 2 });
  const details = Object.entries(guard.category_deltas);
  return (
    <details className="mt-1 pl-3 text-xs">
      <summary className="cursor-pointer font-medium">{t(QUALITY + "guard." + guard.status)}</summary>
      <div className="mt-2 space-y-1 text-hint">
        <p>{t(QUALITY + "policy.protectedIds")} · {guard.protected_count ?? "—"}</p>
        {guard.reasons.map((reason, index) => {
          const key = QUALITY + "issues." + reason.code;
          const label = t(key);
          return (
            <p key={reason.code + "-" + index}>
              {label === key ? <code>{reason.code}</code> : label}
              {reason.category && <> · {reason.category}</>}
              {typeof reason.count === "number" && <> · {reason.count}</>}
            </p>
          );
        })}
        {guard.lost_case_ids.length > 0 && (
          <p className="break-all">{t(QUALITY + "guard.lostCases")} · {guard.lost_case_ids.join(", ")}</p>
        )}
        {guard.new_critical_case_ids.length > 0 && (
          <p className="break-all">{t(QUALITY + "guard.newCriticalCases")} · {guard.new_critical_case_ids.join(", ")}</p>
        )}
        {details.map(([category, values]) => (
          <p key={category}>{category} · {format.format(values.usable_delta * 100)} / {values.minimum === null ? "—" : format.format(values.minimum * 100)} {t(QUALITY + "guard.points")}</p>
        ))}
      </div>
    </details>
  );
}
