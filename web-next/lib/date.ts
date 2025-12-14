export function formatRelativeTime(value?: string | null): string {
  if (!value) return "—";
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) return value;
  const diffMs = Date.now() - target.getTime();
  if (diffMs < 0) return "przyszłość";
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return `${seconds}s temu`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m temu`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h temu`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d temu`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}m-cy temu`;
  const years = Math.floor(months / 12);
  return `${years}y temu`;
}
