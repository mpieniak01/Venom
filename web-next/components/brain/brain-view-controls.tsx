import { Button } from "@/components/ui/button";

import type { BrainGraphViewMode } from "@/lib/types";

export type BrainViewPreset = "session" | "topic" | "pinned" | "recent";

type BrainViewControlsProps = Readonly<{
  title: string;
  mode: BrainGraphViewMode;
  modeLabels: Record<BrainGraphViewMode, string>;
  presetLabels: Record<BrainViewPreset, string>;
  onModeChange: (mode: BrainGraphViewMode) => void;
  onPresetApply: (preset: BrainViewPreset) => void;
}>;

export function BrainViewControls({
  title,
  mode,
  modeLabels,
  presetLabels,
  onModeChange,
  onPresetApply,
}: BrainViewControlsProps) {
  const modes: BrainGraphViewMode[] = ["overview", "focus", "full"];
  const presets: BrainViewPreset[] = ["session", "topic", "pinned", "recent"];

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="brain-view-controls">
      <span className="text-xs uppercase tracking-wide text-zinc-400">{title}</span>
      <div className="flex items-center gap-1 rounded-full border border-white/10 bg-black/40 p-1">
        {modes.map((candidate) => (
          <Button
            key={candidate}
            type="button"
            size="sm"
            variant={mode === candidate ? "secondary" : "ghost"}
            className="rounded-full px-3"
            data-testid={`brain-mode-${candidate}`}
            onClick={() => onModeChange(candidate)}
          >
            {modeLabels[candidate]}
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {presets.map((preset) => (
          <Button
            key={preset}
            type="button"
            size="sm"
            variant="outline"
            className="rounded-full px-3"
            data-testid={`brain-preset-${preset}`}
            onClick={() => onPresetApply(preset)}
          >
            {presetLabels[preset]}
          </Button>
        ))}
      </div>
    </div>
  );
}
