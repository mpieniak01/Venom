"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel } from "@/components/ui/panel";
import type {
  ActiveHiddenPromptsResponse,
  HiddenPromptEntry,
  HiddenPromptsResponse,
} from "@/lib/types";
import { formatRelativeTime } from "@/lib/date";
import { Inbox } from "lucide-react";

type CockpitHiddenPromptsPanelProps = {
  hiddenScoreFilter: number;
  hiddenIntentFilter: string;
  onHiddenIntentFilterChange: (value: string) => void;
  onHiddenScoreFilterChange: (value: number) => void;
  hiddenIntentOptions: string[];
  selectableHiddenPrompts: HiddenPromptEntry[];
  activeHiddenKeys: Set<string>;
  activeHiddenMap: Map<string, HiddenPromptEntry>;
  activeForIntent: HiddenPromptEntry | null;
  hiddenPrompts: HiddenPromptsResponse | null;
  hiddenLoading: boolean;
  hiddenError: string | null;
  activeHiddenLoading: boolean;
  activeHiddenError: string | null;
  onSetActiveHiddenPrompt: (payload: {
    intent?: string;
    prompt?: string;
    approved_response?: string;
    prompt_hash?: string;
    active: boolean;
    actor: string;
  }) => Promise<void>;
};

export function CockpitHiddenPromptsPanel({
  hiddenScoreFilter,
  hiddenIntentFilter,
  onHiddenIntentFilterChange,
  onHiddenScoreFilterChange,
  hiddenIntentOptions,
  selectableHiddenPrompts,
  activeHiddenKeys,
  activeHiddenMap,
  activeForIntent,
  hiddenPrompts,
  hiddenLoading,
  hiddenError,
  activeHiddenLoading,
  activeHiddenError,
  onSetActiveHiddenPrompt,
}: CockpitHiddenPromptsPanelProps) {
  return (
    <Panel
      title="Hidden prompts"
      description={`Agregaty prompt → odpowiedź z /learning/hidden-prompts (score ≥ ${hiddenScoreFilter}).`}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-zinc-400">
        <label className="text-caption">Filtry</label>
        <select
          className="rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-xs text-white"
          value={hiddenIntentFilter}
          onChange={(event) => onHiddenIntentFilterChange(event.target.value)}
        >
          {hiddenIntentOptions.map((intent) => (
            <option key={`intent-${intent}`} value={intent}>
              {intent === "all" ? "Wszystkie intencje" : intent}
            </option>
          ))}
        </select>
        <select
          className="rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-xs text-white"
          value={String(hiddenScoreFilter)}
          onChange={(event) => onHiddenScoreFilterChange(Number(event.target.value))}
        >
          {[1, 2, 3].map((value) => (
            <option key={`score-${value}`} value={String(value)}>
              Score ≥ {value}
            </option>
          ))}
        </select>
        <select
          className="rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-xs text-white"
          value={activeForIntent?.prompt_hash ?? activeForIntent?.prompt ?? ""}
          onChange={async (event) => {
            if (hiddenIntentFilter === "all") return;
            const nextValue = event.target.value;
            if (!nextValue) {
              if (activeForIntent) {
                await onSetActiveHiddenPrompt({
                  intent: activeForIntent.intent,
                  prompt: activeForIntent.prompt,
                  approved_response: activeForIntent.approved_response,
                  prompt_hash: activeForIntent.prompt_hash,
                  active: false,
                  actor: "ui",
                });
              }
              return;
            }
            const candidate = selectableHiddenPrompts.find(
              (entry) => (entry.prompt_hash ?? entry.prompt) === nextValue,
            );
            if (candidate) {
              await onSetActiveHiddenPrompt({
                intent: candidate.intent,
                prompt: candidate.prompt,
                approved_response: candidate.approved_response,
                prompt_hash: candidate.prompt_hash,
                active: true,
                actor: "ui",
              });
            }
          }}
          disabled={hiddenIntentFilter === "all" || selectableHiddenPrompts.length === 0}
        >
          <option value="">
            {hiddenIntentFilter === "all" ? "Wybierz intencję" : "Brak aktywnego"}
          </option>
          {selectableHiddenPrompts.map((entry, idx) => {
            const key = entry.prompt_hash ?? entry.prompt ?? `${idx}`;
            return (
              <option key={`active-hidden-${key}`} value={key}>
                {(entry.prompt ?? "Brak promptu").slice(0, 40)}
              </option>
            );
          })}
        </select>
        {activeHiddenKeys.size > 0 && (
          <span className="pill-badge text-emerald-100">
            Aktywne: {activeHiddenKeys.size}
          </span>
        )}
      </div>
      {hiddenPrompts?.items?.length ? (
        <div className="space-y-3">
          {hiddenPrompts.items.map((entry, idx) => {
            const key = entry.prompt_hash ?? entry.prompt ?? `${idx}`;
            const isActive = activeHiddenKeys.has(key);
            const activeMeta = isActive ? activeHiddenMap.get(key) : undefined;
            return (
              <div
                key={`hidden-${entry.intent ?? "unknown"}-${idx}`}
                className="rounded-2xl box-muted p-3 text-xs text-zinc-300"
              >
                <div className="flex flex-wrap items-center gap-2 text-caption">
                  <Badge tone="neutral">Score: {entry.score ?? 1}</Badge>
                  <span>{entry.intent ?? "—"}</span>
                  <span>{formatRelativeTime(entry.last_timestamp)}</span>
                  {isActive && (
                    <Badge tone="success">
                      Aktywny
                      {activeMeta?.activated_by ? ` • ${activeMeta.activated_by}` : ""}
                    </Badge>
                  )}
                </div>
                <p className="mt-2 text-sm text-white">
                  {(entry.prompt ?? "Brak promptu.").slice(0, 160)}
                </p>
                {entry.approved_response && (
                  <p className="mt-2 text-hint">
                    {entry.approved_response.slice(0, 160)}
                  </p>
                )}
                {activeMeta?.activated_at && (
                  <p className="mt-2 text-hint text-emerald-200">
                    Aktywne od: {formatRelativeTime(activeMeta.activated_at)}
                  </p>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    size="xs"
                    variant={isActive ? "danger" : "outline"}
                    onClick={async () => {
                      await onSetActiveHiddenPrompt({
                        intent: entry.intent,
                        prompt: entry.prompt,
                        approved_response: entry.approved_response,
                        prompt_hash: entry.prompt_hash,
                        active: !isActive,
                        actor: "ui",
                      });
                    }}
                  >
                    {isActive ? "Wyłącz" : "Aktywuj"}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyState
          icon={<Inbox className="h-4 w-4" />}
          title="Brak hidden prompts"
          description="Pojawią się po ocenach z kciukiem w górę."
        />
      )}
      {hiddenLoading && <p className="mt-2 text-hint">Ładowanie hidden prompts...</p>}
      {hiddenError && <p className="mt-2 text-xs text-rose-300">{hiddenError}</p>}
      {activeHiddenLoading && (
        <p className="mt-2 text-hint">Ładowanie aktywnych wpisów...</p>
      )}
      {activeHiddenError && (
        <p className="mt-2 text-xs text-rose-300">{activeHiddenError}</p>
      )}
    </Panel>
  );
}
