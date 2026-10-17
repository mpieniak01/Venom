"use client";

import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ConfigSection({
  title,
  description,
  children,
  forceOpen = false,
}: Readonly<{
  title: string;
  description: string;
  children: React.ReactNode;
  forceOpen?: boolean;
}>) {
  const [open, setOpen] = useState(false);
  const contentId = useId();
  const expanded = open || forceOpen;

  return (
    <div className="glass-panel rounded-2xl box-subtle p-6">
      <Button
        type="button"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={() => setOpen((prev) => !prev)}
        disabled={forceOpen}
        variant="ghost"
        size="sm"
        className="w-full items-start justify-between gap-4 text-left"
      >
        <div>
          <h3 className="heading-h3">{title}</h3>
          <p className="mt-1 text-hint">{description}</p>
        </div>
        <ChevronDown
          className={`mt-1 h-5 w-5 text-zinc-500 transition-transform duration-300 ${expanded ? "rotate-180" : ""}`}
        />
      </Button>
      <div
        id={contentId}
        hidden={!expanded}
        className="min-w-0"
      >
        <div className="pt-4 space-y-4">{children}</div>
      </div>
    </div>
  );
}
