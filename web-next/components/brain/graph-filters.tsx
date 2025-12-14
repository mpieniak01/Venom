"use client";

import { Button } from "@/components/ui/button";

export type GraphFilterType = "all" | "agent" | "memory" | "file" | "function";

type GraphFilterButtonsProps = {
  activeFilter: GraphFilterType;
  onFilterChange: (value: GraphFilterType) => void;
};

const FILTER_OPTIONS: GraphFilterType[] = ["all", "agent", "memory", "file", "function"];

export function GraphFilterButtons({ activeFilter, onFilterChange }: GraphFilterButtonsProps) {
  return (
    <div className="flex flex-wrap gap-2 rounded-2xl border border-white/10 bg-black/70 px-4 py-3 text-xs text-white backdrop-blur">
      {FILTER_OPTIONS.map((type) => (
        <Button
          key={type}
          size="xs"
          variant={activeFilter === type ? "primary" : "outline"}
          className="px-3"
          onClick={() => onFilterChange(type)}
        >
          {type}
        </Button>
      ))}
    </div>
  );
}
