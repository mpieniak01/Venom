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

export function formatUsd(value?: number, fractionDigits = 4) {
  return typeof value === "number" ? `$${value.toFixed(fractionDigits)}` : "—";
}
