"use client";

import { useEffect, useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useRouter } from "next/navigation";
import { Command, Loader2, Search } from "lucide-react";
import { navItems } from "./sidebar";
import { useTranslation } from "@/lib/i18n";

type CommandPaletteProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenQuickActions: () => void;
};

type PaletteAction = {
  id: string;
  label: string;
  description: string;
  category: string;
  run: () => Promise<void> | void;
};

export function CommandPalette({ open, onOpenChange, onOpenQuickActions }: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [running, setRunning] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const t = useTranslation();

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const navActions: PaletteAction[] = useMemo(
    () =>
      navItems.map((item) => {
        const label = item.labelKey ? t(item.labelKey) : item.label;
        return {
          id: `nav-${item.href}`,
          label,
          description: `${t("commandPalette.goTo")} ${label}.`,
          category: t("commandPalette.navCategory"),
          run: () => {
            router.push(item.href);
          },
        };
      }),
    [router, t],
  );

  const queueActions: PaletteAction[] = useMemo(
    () => [
      {
        id: "queue-open",
        label: t("commandPalette.openQuickActions"),
        description: t("commandPalette.openQuickActionsDesc"),
        category: t("commandPalette.queueCategory"),
        run: async () => {
          onOpenQuickActions();
        },
      },
    ],
    [onOpenQuickActions, t],
  );

  const allActions = [...navActions, ...queueActions];
  const filtered = allActions.filter((action) =>
    action.label.toLowerCase().includes(query.toLowerCase()),
  );

  const grouped = useMemo(() => {
    return filtered.reduce<Record<string, PaletteAction[]>>((acc, action) => {
      acc[action.category] = acc[action.category] || [];
      acc[action.category].push(action);
      return acc;
    }, {});
  }, [filtered]);

  const handleRun = async (action: PaletteAction) => {
    try {
      setRunning(action.id);
      setMessage(null);
      await action.run();
      setMessage(`${action.label} ${t("commandPalette.runSuccess")}`);
      onOpenChange(false);
    } catch (err) {
      setMessage(
        err instanceof Error
          ? err.message
          : `${t("commandPalette.runError")}: ${action.label}`,
      );
    } finally {
      setRunning(null);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in data-[state=closed]:fade-out" />
      <Dialog.Content className="card-shell fixed left-1/2 top-24 z-50 w-full max-w-3xl -translate-x-1/2 bg-zinc-950/95 p-6 shadow-2xl focus:outline-none">
          <div className="mb-4 flex items-center gap-3">
            <div className="rounded-2xl bg-white/5 p-2 text-violet-200">
              <Command className="h-5 w-5" />
            </div>
            <div>
              <Dialog.Title className="text-lg font-semibold">{t("commandPalette.title")}</Dialog.Title>
              <Dialog.Description className="text-sm text-zinc-500">
                {t("commandPalette.description")}
              </Dialog.Description>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-white">
            <Search className="h-4 w-4 text-zinc-500" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full bg-transparent text-sm outline-none placeholder:text-zinc-500"
              placeholder={t("commandPalette.searchPlaceholder")}
            />
            <span className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-zinc-400">
              ⌘K
            </span>
          </div>
          <div className="mt-4 max-h-[50vh] space-y-4 overflow-y-auto">
            {Object.entries(grouped).map(([category, actions]) => (
              <div key={category}>
                <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">{category}</p>
                <div className="mt-2 space-y-2">
                  {actions.map((action) => (
                    <button
                      key={action.id}
                      className="flex w-full items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-left text-sm text-white transition hover:border-violet-500/40 hover:bg-violet-500/10"
                      onClick={() => handleRun(action)}
                      disabled={!!running}
                    >
                      <div>
                        <p className="font-semibold">{action.label}</p>
                        <p className="text-xs text-zinc-400">{action.description}</p>
                      </div>
                      {running === action.id && <Loader2 className="h-4 w-4 animate-spin text-violet-300" />}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            {filtered.length === 0 && (
              <p className="text-sm text-zinc-500">{t("commandPalette.empty")}</p>
            )}
          </div>
          {message && (
            <div className="mt-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-zinc-300">
              {message}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
