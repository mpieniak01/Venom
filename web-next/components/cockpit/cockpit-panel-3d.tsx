"use client";

import { motion } from "framer-motion";
import type { PropsWithChildren } from "react";

type CockpitPanel3DProps = PropsWithChildren<{
  fullscreen: boolean;
}>;

export function CockpitPanel3D({ fullscreen, children }: CockpitPanel3DProps) {
  return (
    <motion.div
      className="glass-panel command-console-panel relative flex min-h-[520px] min-h-0 h-[calc(100vh-220px)] max-h-[calc(100vh-220px)] flex-col overflow-hidden px-6 py-6"
      key={fullscreen ? "chat-fullscreen" : "chat-default"}
      initial={{ opacity: 0, y: 24, scale: 0.98, rotateX: 6, rotateY: -6 }}
      animate={{
        opacity: 1,
        y: 0,
        scale: fullscreen ? 1.01 : 1,
        rotateX: 0,
        rotateY: 0,
      }}
      transition={{ duration: 1.05, ease: [0.4, 0, 1, 1] }}
      style={{ transformStyle: "preserve-3d", perspective: 1200 }}
    >
      {children}
    </motion.div>
  );
}
