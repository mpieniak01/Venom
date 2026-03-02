import { cn } from "@/lib/utils";

export const THEME_TAB_BAR_CLASS =
  "flex flex-wrap gap-2 border-b border-[color:var(--ui-border)]";

const THEME_TAB_BASE_CLASS =
  "gap-2 rounded-t-xl rounded-b-none border-b-2 border-transparent px-4 py-3 text-sm font-medium text-[color:var(--ui-muted)] hover:bg-[color:var(--ui-surface-hover)] hover:text-[color:var(--text-primary)]";

const THEME_TAB_ACTIVE_CLASS =
  "border-[color:var(--accent)] bg-[color:var(--primary-dim)] text-[color:var(--text-primary)]";

export function getThemeTabClass(active: boolean) {
  return cn(THEME_TAB_BASE_CLASS, active ? THEME_TAB_ACTIVE_CLASS : null);
}
