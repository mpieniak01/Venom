"use client";

import { Button } from "@/components/ui/button";
import { Layers, Scan } from "lucide-react";
import { useTranslation } from "@/lib/i18n";

type GraphActionButtonsProps = {
  onFit: () => void;
  onScan: () => Promise<void> | void;
  scanning: boolean;
  scanMessage?: string | null;
};

export function GraphActionButtons({ onFit, onScan, scanning, scanMessage }: GraphActionButtonsProps) {
  const t = useTranslation();
  return (
    <div className="flex flex-col items-end gap-2 rounded-2xl border border-white/10 bg-black/70 px-4 py-3 text-sm text-white backdrop-blur">
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={onFit}>
          <Layers className="h-4 w-4" />
          {t("brain.graph.fit")}
        </Button>
        <Button variant="primary" size="sm" disabled={scanning} onClick={onScan}>
          <Scan className="h-4 w-4" />
          {scanning ? t("brain.graph.scanning") : t("brain.graph.scan")}
        </Button>
      </div>
      {scanMessage && (
        <p className="text-xs text-zinc-300" data-testid="graph-scan-message">
          {scanMessage}
        </p>
      )}
    </div>
  );
}
