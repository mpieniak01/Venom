import { notFound } from "next/navigation";

import { ModuleHostFallback } from "@/components/modules/module-host-fallback";
import {
  getOptionalModuleComponent,
  resolveOptionalModuleBySlug,
} from "@/lib/generated/optional-modules.generated";

type OptionalModulePageProps = {
  params: Promise<{
    moduleSlug: string;
  }>;
};

function isFeatureEnabled(flagName: string | null): boolean {
  if (!flagName) {
    return true;
  }
  const raw = process.env[flagName];
  if (!raw) {
    return false;
  }
  const normalized = raw.trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes" || normalized === "on";
}

export default async function OptionalModulePage({ params }: Readonly<OptionalModulePageProps>) {
  const resolvedParams = await params;
  const manifest = resolveOptionalModuleBySlug(resolvedParams.moduleSlug);
  if (!manifest) {
    notFound();
  }
  if (!isFeatureEnabled(manifest.featureFlagEnv)) {
    notFound();
  }

  const ModuleComponent = getOptionalModuleComponent(manifest.moduleId);
  if (ModuleComponent) {
    return <ModuleComponent />;
  }

  return (
    <ModuleHostFallback
      moduleName={manifest.displayName}
      moduleId={manifest.moduleId}
      modulePath={manifest.routePath}
    />
  );
}
