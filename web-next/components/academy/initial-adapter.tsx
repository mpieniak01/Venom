"use client";

import { useState } from "react";
import { Label } from "@/components/ui/label";
import type { ExperimentInitialAdapter } from "@/lib/academy-experiments-api";
import { useTranslation } from "@/lib/i18n";

const INITIAL_ADAPTER = "academy.campaigns.initialAdapter.";

export function initialAdapterField(row: number) {
  return `variant-${row}-initial-adapter`;
}

export function InitialAdapterSelector({ row, index, adapters, disabled }: {
  readonly row: number;
  readonly index: number;
  readonly adapters: ExperimentInitialAdapter[];
  readonly disabled: boolean;
}) {
  const t = useTranslation();
  const [selectedId, setSelectedId] = useState("");
  const selected = adapters.find((adapter) => adapter.adapter_id === selectedId);
  const selectionUnavailable = Boolean(selectedId && !selected);
  const field = initialAdapterField(row);

  return (
    <div className="space-y-1">
      <Label htmlFor={field}>{t(INITIAL_ADAPTER + "label")} {index + 1}</Label>
      <input type="hidden" name={field} value={selectedId} />
      <select id={field} value={selectedId} disabled={disabled} aria-invalid={selectionUnavailable}
        className="h-9 w-full rounded-md border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-2 text-sm"
        onChange={(event) => setSelectedId(event.currentTarget.value)}>
        <option value="">{t(INITIAL_ADAPTER + "fresh")}</option>
        {adapters.map((adapter) => (
          <option key={adapter.adapter_id} value={adapter.adapter_id}>{adapter.label} · {adapter.adapter_id}</option>
        ))}
        {selectionUnavailable && <option value={selectedId} disabled>{selectedId} · {t(INITIAL_ADAPTER + "unavailable")}</option>}
      </select>
      {selected && <InitialAdapterSummary adapter={selected} />}
    </div>
  );
}

export function InitialAdapterSummary({ adapter }: { readonly adapter?: ExperimentInitialAdapter | null }) {
  const t = useTranslation();
  if (!adapter) return <p className="text-xs text-hint">{t(INITIAL_ADAPTER + "fresh")}</p>;

  return (
    <div className="space-y-1 text-xs">
      <p className="break-words">{t(INITIAL_ADAPTER + "registered")} · {adapter.label} · <code>{adapter.adapter_id}</code></p>
      <p className="break-all text-hint">
        {t("academy.experiments.model")} {adapter.model} @ <code title={adapter.revision}>{adapter.revision.slice(0, 12)}</code>
      </p>
      <p className="break-all text-hint">
        {t(INITIAL_ADAPTER + "weights")} <code title={adapter.weights_sha256}>{adapter.weights_sha256.slice(0, 12)}</code>
        {" · "}{t(INITIAL_ADAPTER + "source")} {adapter.source.identity}
      </p>
    </div>
  );
}

export function useInitialAdapterError(code?: string | null) {
  const t = useTranslation();
  if (!code) return null;
  const key = INITIAL_ADAPTER + "errors." + code;
  const message = t(key);
  return message === key ? null : message;
}
