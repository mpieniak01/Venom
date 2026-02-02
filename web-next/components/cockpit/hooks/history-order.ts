import { type SessionHistoryEntry } from "@/components/cockpit/cockpit-hooks";

export function orderHistoryEntriesByRequestId(
  entries: SessionHistoryEntry[],
): SessionHistoryEntry[] {
  const withRequestId = entries.filter((entry) => entry.request_id);
  const withoutRequestId = entries.filter((entry) => !entry.request_id);

  const grouped = new Map<
    string,
    { user?: SessionHistoryEntry; assistant?: SessionHistoryEntry; other?: SessionHistoryEntry[] }
  >();

  withRequestId.forEach((entry) => {
    const key = String(entry.request_id);
    const bucket = grouped.get(key) || {};
    if (entry.role === "user") {
      if (bucket.user) {
        bucket.other = [...(bucket.other || []), entry];
      } else {
        bucket.user = entry;
      }
    } else if (entry.role === "assistant") {
      if (bucket.assistant) {
        bucket.other = [...(bucket.other || []), entry];
      } else {
        bucket.assistant = entry;
      }
    } else {
      bucket.other = [...(bucket.other || []), entry];
    }
    grouped.set(key, bucket);
  });

  const ordered: SessionHistoryEntry[] = [];
  const groupList = Array.from(grouped.entries()).map(([requestId, bucket]) => {
    const ts = bucket.user?.timestamp || bucket.assistant?.timestamp || "";
    return { requestId, bucket, ts };
  });

  groupList.sort(
    (a, b) => new Date(a.ts || 0).getTime() - new Date(b.ts || 0).getTime(),
  );

  groupList.forEach(({ bucket }) => {
    if (bucket.user) ordered.push(bucket.user);
    if (bucket.assistant) ordered.push(bucket.assistant);
    if (bucket.other && bucket.other.length > 0) {
      ordered.push(...bucket.other);
    }
  });

  if (withoutRequestId.length > 0) {
    withoutRequestId.sort(
      (a, b) =>
        new Date(a.timestamp || 0).getTime() -
        new Date(b.timestamp || 0).getTime(),
    );
    ordered.push(...withoutRequestId);
  }

  return ordered;
}
