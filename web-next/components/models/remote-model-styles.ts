/** Shared surfaces and controls matching the existing Models / Remote Models panels. */
export const remoteModelStyles = {
  panel: "min-w-0 rounded-[24px] border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4 text-sm text-[color:var(--text-primary)] shadow-card sm:p-6",
  card: "min-w-0 rounded-2xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4",
  heading: "text-[10px] font-medium uppercase tracking-[0.35em] text-[color:var(--ui-muted)]",
  label: "flex min-w-0 flex-col gap-2 text-xs font-medium text-[color:var(--text-primary)]",
  input: "h-10 w-full min-w-0 rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-3 text-sm text-[color:var(--text-primary)] outline-none transition placeholder:text-[color:var(--ui-muted)] focus-visible:border-[color:var(--ui-border-strong)] focus-visible:ring-2 focus-visible:ring-[color:var(--primary)] disabled:cursor-not-allowed disabled:opacity-60",
  hint: "text-xs leading-relaxed text-[color:var(--ui-muted)]",
  tableWrap: "max-w-full overflow-auto rounded-2xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)]",
  tableHead: "whitespace-nowrap px-4 py-3 text-left text-[11px] font-medium uppercase tracking-wider text-[color:var(--ui-muted)]",
  tableRow: "border-t border-[color:var(--ui-border)] transition-colors hover:bg-[color:var(--ui-surface-hover)]",
  tableCell: "px-4 py-3 text-xs",
} as const;
