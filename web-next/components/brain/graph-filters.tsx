"use client";

import { Button } from "@/components/ui/button";

export type GraphFilterType = "all" | "agent" | "memory" | "file" | "function";

type GraphFilterButtonsProps = {
  selectedFilters: GraphFilterType[];
  onToggleFilter: (value: GraphFilterType) => void;
};

const FILTER_OPTIONS: GraphFilterType[] = ["all", "agent", "memory", "file", "function"];

export function GraphFilterButtons({ selectedFilters, onToggleFilter }: GraphFilterButtonsProps) {
  const isActive = (type: GraphFilterType) => selectedFilters.includes(type);

  return (
    <div className="flex flex-wrap gap-2 rounded-2xl border border-white/10 bg-black/70 px-4 py-3 text-xs text-white backdrop-blur">
      {FILTER_OPTIONS.map((type) => (
        <Button
          key={type}
          size="xs"
          variant={isActive(type) ? "primary" : "outline"}
          className="px-3 capitalize"
          onClick={() => onToggleFilter(type)}
        >
          {type}
        </Button>
      ))}
    </div>
  );
}
