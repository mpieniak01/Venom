type HasIdAndTimestamp = {
  id: string;
  timestamp: string;
};

export function mergeAuditEntries<T extends HasIdAndTimestamp>(
  currentEntries: T[],
  incomingEntries: T[]
): T[] {
  if (!incomingEntries.length) return currentEntries;
  const merged = [...currentEntries];
  const seen = new Set(currentEntries.map((entry) => `${entry.id}:${entry.timestamp}`));
  incomingEntries.forEach((entry) => {
    const key = `${entry.id}:${entry.timestamp}`;
    if (seen.has(key)) return;
    seen.add(key);
    merged.push(entry);
  });
  return merged;
}

export function isNearBottom(
  scrollHeight: number,
  scrollTop: number,
  clientHeight: number,
  threshold = 120
): boolean {
  return scrollHeight - scrollTop - clientHeight <= threshold;
}

export function nextVisibleCount(
  currentVisibleCount: number,
  totalRows: number,
  batchSize: number
): number {
  return Math.min(currentVisibleCount + batchSize, totalRows);
}
