"use client";

import { Suspense } from "react";
import { AcademyDashboard } from "@/components/academy/academy-dashboard";

export default function AcademyPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[400px] items-center justify-center">
          <div className="text-zinc-400">Ładowanie Academy...</div>
        </div>
      }
    >
      <AcademyDashboard />
    </Suspense>
  );
}
