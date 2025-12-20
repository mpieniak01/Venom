export function formatPercentMetric(value?: number, digits = 1) {
  return typeof value === "number" ? `${value.toFixed(digits)}%` : "—";
}

export function formatGbPair(used?: number, total?: number) {
  if (typeof used === "number" && typeof total === "number") {
    return `${used.toFixed(1)} / ${total.toFixed(1)} GB`;
  }
  return "—";
}

export function formatVramMetric(usedMb?: number, totalMb?: number) {
  if (typeof usedMb === "number" && typeof totalMb === "number" && totalMb > 0) {
    const usedGb = usedMb / 1024;
    const totalGb = totalMb / 1024;
    return `${usedGb.toFixed(1)} / ${totalGb.toFixed(1)} GB`;
  }
  if (typeof usedMb === "number" && usedMb > 0) {
    return `${(usedMb / 1024).toFixed(1)} GB`;
  }
  return "—";
}

export function formatDiskUsage(usedGb?: number, limitGb?: number) {
  if (typeof usedGb === "number" && typeof limitGb === "number") {
    return `${usedGb.toFixed(2)} GB / ${limitGb.toFixed(0)} GB`;
  }
  return "—";
}

function formatDiskUnit(valueGb: number, preferTb = false) {
  if (valueGb >= 1024 || preferTb) {
    return `${(valueGb / 1024).toFixed(1)}T`;
  }
  const digits = valueGb >= 100 ? 0 : 1;
  return `${valueGb.toFixed(digits)}G`;
}

export function formatDiskSnapshot(usedGb?: number, totalGb?: number) {
  if (typeof usedGb !== "number" || typeof totalGb !== "number") {
    return "—";
  }
  const freeGb = Math.max(totalGb - usedGb, 0);
  const useTb = totalGb >= 1024;
  const totalLabel = formatDiskUnit(totalGb, useTb);
  const usedLabel = formatDiskUnit(usedGb, useTb);
  const freeLabel = formatDiskUnit(freeGb, false);
  return `${totalLabel}/${usedLabel} - ${freeLabel}`;
}

export function formatUsd(value?: number, fractionDigits = 4) {
  return typeof value === "number" ? `$${value.toFixed(fractionDigits)}` : "—";
}
