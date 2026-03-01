"use client";

import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ConfigSection({
  title,
  description,
  children,
}: Readonly<{
  title: string;
  description: string;
  children: React.ReactNode;
}>) {
  const [open, setOpen] = useState(false);
  const contentId = useId();

  return (
    <div className="glass-panel rounded-2xl box-subtle p-6">
      <Button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((prev) => !prev)}
        variant="ghost"
        size="sm"
        className="w-full items-start justify-between gap-4 text-left"
      >
        <div>
          <h3 className="heading-h3">{title}</h3>
          <p className="mt-1 text-hint">{description}</p>
        </div>
        <ChevronDown
          className={`mt-1 h-5 w-5 text-zinc-500 transition-transform duration-300 ${open ? "rotate-180" : ""}`}
        />
      </Button>
      <div
        id={contentId}
        className={`overflow-hidden transition-[max-height,opacity,transform] duration-300 ease-out ${open ? "max-h-[1200px] opacity-100 translate-y-0" : "max-h-0 opacity-0 -translate-y-1"}`}
      >
        <div className="pt-4 space-y-4">{children}</div>
      </div>
    </div>
  );
}
