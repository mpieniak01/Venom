"use client";

import { QuickActions } from "@/components/layout/quick-actions";

type CockpitActionsProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function CockpitActions({ open, onOpenChange }: CockpitActionsProps) {
  return <QuickActions open={open} onOpenChange={onOpenChange} />;
}
