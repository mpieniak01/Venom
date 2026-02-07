"use client";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel } from "@/components/ui/panel";
import { HelpCircle, Package } from "lucide-react";
import Link from "next/link";
import type { SelectMenuOption } from "@/components/ui/select-menu";
import { SelectMenu } from "@/components/ui/select-menu";
import type { LlmServerInfo } from "@/lib/types";

type CockpitModelsProps = {
  llmServersLoading: boolean;
  llmServers: LlmServerInfo[];
  selectedLlmServer: string;
  llmServerOptions: SelectMenuOption[];
  onSelectLlmServer: (value: string) => void;
  selectedLlmModel: string;
  llmModelOptions: SelectMenuOption[];
  onSelectLlmModel: (value: string) => void;
  availableModelsForServer: Array<{ name?: string }>;
  selectedServerEntry?: LlmServerInfo | null;
  resolveServerStatus: (displayName?: string, status?: string | null) => string;
  sessionId: string;
  memoryAction: "session" | "global" | null;
  onSessionReset: () => void;
  onServerSessionReset: () => void;
  onClearSessionMemory: () => void;
  onClearGlobalMemory: () => void;
  activeServerInfo?: { active_model?: string | null } | null;
  activeServerName?: string | null;
  llmActionPending: string | null;
  onActivateServer: () => void;
};

export function CockpitModels({
  llmServersLoading,
  llmServers,
  selectedLlmServer,
  llmServerOptions,
  onSelectLlmServer,
  selectedLlmModel,
  llmModelOptions,
  onSelectLlmModel,
  availableModelsForServer,
  selectedServerEntry,
  resolveServerStatus,
  sessionId,
  memoryAction,
  onSessionReset,
  onServerSessionReset,
  onClearSessionMemory,
  onClearGlobalMemory,
  activeServerInfo,
  activeServerName,
  llmActionPending,
  onActivateServer,
}: CockpitModelsProps) {
  return (
    <Panel
      title="Serwery LLM"
      description="Steruj lokalnymi runtime (vLLM, Ollama) i monitoruj ich status."
      className="allow-overflow overflow-visible"
    >
      <div className="space-y-3">
        {llmServersLoading ? (
          <p className="text-hint">Ładuję status serwerów…</p>
        ) : llmServers.length === 0 ? (
          <EmptyState
            icon={<Package className="h-4 w-4" />}
            title="Brak danych"
            description="Skonfiguruj komendy LLM_*_COMMAND w .env, aby włączyć sterowanie serwerami."
          />
        ) : null}
        <div className="card-shell card-base p-4 text-sm">
          <div className="grid gap-3">
            <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
              Serwer
            </p>
            <SelectMenu
              value={selectedLlmServer}
              options={llmServerOptions}
              onChange={onSelectLlmServer}
              ariaLabel="Wybierz serwer LLM"
              placeholder="Wybierz serwer"
              disabled={llmServers.length === 0}
              buttonClassName="w-full justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
              menuClassName="w-full max-h-72 overflow-y-auto"
            />
            <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
              Model
            </p>
            <SelectMenu
              value={selectedLlmModel}
              options={llmModelOptions}
              onChange={onSelectLlmModel}
              ariaLabel="Wybierz model LLM"
              placeholder="Brak modeli"
              disabled={llmServers.length === 0 || availableModelsForServer.length === 0}
              buttonClassName="w-full justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
              menuClassName="w-full max-h-72 overflow-y-auto"
            />
            {selectedLlmServer && availableModelsForServer.length === 0 && (
              <div className="space-y-2">
                <EmptyState
                  icon={<Package className="h-4 w-4" />}
                  title="Brak modeli"
                  description="Dodaj model dla wybranego serwera, aby go aktywować."
                />
              </div>
            )}
            <Link
              href="/docs/llm-models"
              className="group inline-flex cursor-pointer items-center gap-2 text-xs underline underline-offset-2 transition hover:opacity-90 !text-[color:var(--secondary)]"
            >
              <HelpCircle
                className="h-4 w-4 transition group-hover:opacity-90 !text-[color:var(--secondary)]"
                aria-hidden="true"
              />
              <span className="!text-[color:var(--secondary)]">
                Instrukcja dodawania modeli
              </span>
            </Link>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400">
            <span>
              Status:{" "}
              {selectedServerEntry
                ? resolveServerStatus(
                    selectedServerEntry.display_name,
                    selectedServerEntry.status,
                  )
                : "unknown"}
            </span>
            <span className="flex flex-wrap items-center gap-2">
              <span
                className="rounded bg-muted px-2 py-1 text-[11px] text-foreground"
                title="Id sesji"
              >
                {sessionId}
              </span>
              <Button
                size="xs"
                variant="ghost"
                onClick={onSessionReset}
                title="Resetuj kontekst czatu (nowa sesja)"
              >
                Resetuj sesję
              </Button>
              <Button
                size="xs"
                variant="ghost"
                onClick={onServerSessionReset}
                disabled={memoryAction === "session"}
                title="Nowa sesja serwera: wyczyść pamięć/streszczenie i utwórz nową sesję"
              >
                {memoryAction === "session" ? "Resetuję..." : "Nowa sesja serwera"}
              </Button>
              <Button
                size="xs"
                variant="ghost"
                onClick={onClearSessionMemory}
                disabled={memoryAction === "session"}
                title="Usuń historię/streszczenia i wektory tej sesji"
              >
                {memoryAction === "session" ? "Czyszczę..." : "Wyczyść pamięć sesji"}
              </Button>
              <Button
                size="xs"
                variant="ghost"
                onClick={onClearGlobalMemory}
                disabled={memoryAction === "global"}
                title="Usuń globalne preferencje/fakty (LanceDB)"
              >
                {memoryAction === "global" ? "Czyszczę..." : "Wyczyść pamięć globalną"}
              </Button>
            </span>
            <span>
              Aktywny: {activeServerInfo?.active_model ?? "—"} @{" "}
              {activeServerName || "—"}
            </span>
          </div>
          <Button
            variant="macro"
            size="sm"
            className="mt-4 w-full justify-center text-center tracking-[0.2em]"
            onClick={onActivateServer}
            disabled={
              llmActionPending === `activate:${selectedLlmServer}` ||
              !selectedLlmServer ||
              !selectedLlmModel
            }
          >
            {llmActionPending === `activate:${selectedLlmServer}`
              ? "Aktywuję..."
              : "Aktywuj"}
          </Button>
        </div>
      </div>
    </Panel>
  );
}
