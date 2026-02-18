"use client";

import { useTranslation } from "@/lib/i18n";

type ModuleHostFallbackProps = {
  moduleName: string;
  moduleId: string;
  modulePath: string;
};

export function ModuleHostFallback({ moduleName, moduleId, modulePath }: Readonly<ModuleHostFallbackProps>) {
  const t = useTranslation();
  return (
    <section className="card-shell p-6">
      <p className="eyebrow">{t("moduleHost.eyebrow")}</p>
      <h1 className="mt-2 text-3xl font-semibold text-white">{moduleName}</h1>
      <p className="mt-2 text-sm text-zinc-300">{t("moduleHost.noFrontend")}</p>
      <dl className="mt-4 space-y-1 text-xs text-zinc-400">
        <div>
          <dt className="inline font-semibold text-zinc-300">{t("moduleHost.moduleId")}:</dt>{" "}
          <dd className="inline">{moduleId}</dd>
        </div>
        <div>
          <dt className="inline font-semibold text-zinc-300">{t("moduleHost.route")}:</dt>{" "}
          <dd className="inline">{modulePath}</dd>
        </div>
      </dl>
    </section>
  );
}
