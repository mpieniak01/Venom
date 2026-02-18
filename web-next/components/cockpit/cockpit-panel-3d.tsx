"use client";

import { motion } from "framer-motion";
import type { PropsWithChildren } from "react";
import { cn } from "@/lib/utils";

type CockpitPanel3DProps = PropsWithChildren<{
  fullscreen: boolean;
}>;

export function CockpitPanel3D({ fullscreen, children }: CockpitPanel3DProps) {
  return (
    <motion.div
      className={cn(
        "glass-panel command-console-panel relative flex flex-col !overflow-hidden px-6 py-6",
        fullscreen
          ? "h-[calc(100dvh-6.5rem)] min-h-[640px]"
          : "h-[76dvh] min-h-[620px] max-h-[980px]",
      )}
      initial={false}
      layout
      animate={{
        scale: fullscreen ? 1.002 : 1, // Subtle scale
      }}
      transition={{
        layout: { duration: 0.4, ease: [0.4, 0, 0.2, 1] }, // Smooth dynamic resize
        scale: { duration: 0.4 },
      }}
      style={{ transformStyle: "preserve-3d", perspective: 1200 }}
    >
      {children}
    </motion.div>
  );
}
