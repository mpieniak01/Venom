"use client";

import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { Command } from "lucide-react";

type CockpitHeaderProps = {
  showReferenceSections: boolean;
  showArtifacts: boolean;
  onToggleArtifacts: () => void;
};

export function CockpitHeader({
  showReferenceSections,
  showArtifacts,
  onToggleArtifacts,
}: CockpitHeaderProps) {
  return (
    <SectionHeading
      eyebrow="Dashboard Control"
      title="Centrum Dowodzenia AI"
      description={
        <span className="text-zinc-200">
          Monitoruj telemetrię, kolejkę i logi w czasie rzeczywistym – reaguj tak szybko, jak Venom OS.
        </span>
      }
      as="h1"
      size="lg"
      rightSlot={
        <div className="flex items-center gap-3">
          {!showReferenceSections && (
            <Button
              size="sm"
              variant="outline"
              className="text-zinc-200"
              onClick={onToggleArtifacts}
            >
              {showArtifacts ? "Ukryj panele" : "Pokaż panele"}
            </Button>
          )}
          <Command className="page-heading-icon" />
        </div>
      }
    />
  );
}
