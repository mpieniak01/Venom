"use client";

import { useTranslation } from "@/lib/i18n";

export default function ModuleExampleModulePage() {
  const t = useTranslation();

  return (
    <section className="card-shell p-6">
      <p className="eyebrow">{t("moduleExample.eyebrow")}</p>
      <h1 className="mt-2 text-3xl font-semibold text-white">{t("sidebar.nav.moduleExample")}</h1>
      <p className="mt-2 text-sm text-zinc-300">{t("moduleExample.description")}</p>
    </section>
  );
}
