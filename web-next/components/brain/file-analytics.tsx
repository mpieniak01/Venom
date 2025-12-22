"use client";

import { Button } from "@/components/ui/button";

type FileAnalysisFormProps = {
  filePath: string;
  onPathChange: (value: string) => void;
  loading: boolean;
  onFileInfo: () => void;
  onImpact: () => void;
  message?: string | null;
};

export function FileAnalysisForm({
  filePath,
  onPathChange,
  loading,
  onFileInfo,
  onImpact,
  message,
}: FileAnalysisFormProps) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <input
          className="w-full flex-1 rounded-2xl box-base px-3 py-2 text-sm text-white outline-none focus:border-[--color-accent]"
          placeholder="venom_core/api/routes/system.py"
          value={filePath}
          onChange={(e) => onPathChange(e.target.value)}
        />
        <Button variant="outline" size="sm" disabled={loading} onClick={onFileInfo}>
          ℹ️ Info
        </Button>
        <Button variant="outline" size="sm" disabled={loading} onClick={onImpact}>
          🌐 Impact
        </Button>
      </div>
      {message && <p className="text-hint">{message}</p>}
    </div>
  );
}

type FileAnalysisPanelProps = {
  label: string;
  payload: Record<string, unknown> | null;
};

export function FileAnalysisPanel({ label, payload }: FileAnalysisPanelProps) {
  return (
    <div className="rounded-2xl box-muted p-4 text-xs text-muted">
      <p className="text-sm font-semibold text-white">{label}</p>
      {payload ? (
        <pre className="mt-2 max-h-64 overflow-auto rounded-xl box-muted p-2 text-xs text-zinc-100">
          {JSON.stringify(payload, null, 2)}
        </pre>
      ) : (
        <p className="mt-2 text-hint">Brak danych.</p>
      )}
    </div>
  );
}
