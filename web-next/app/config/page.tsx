"use client";

import { Suspense } from "react";
import { ConfigHome } from "@/components/config/config-home";
import { useTranslation } from "@/lib/i18n";

export default function ConfigPage() {
  const t = useTranslation();

  return (
    <Suspense
      fallback={
        <div className="flex min-h-[400px] items-center justify-center">
          <div className="text-zinc-400">{t("common.loading")}</div>
        </div>
      }
    >
      <ConfigHome />
    </Suspense>
  );
}
