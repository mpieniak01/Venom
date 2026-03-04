import "server-only";

import type { ComponentType } from "react";

type OptionalModuleComponent = ComponentType | null;

const OPTIONAL_MODULE_COMPONENT_LOADERS: Record<
  string,
  () => Promise<OptionalModuleComponent>
> = {
  brand_studio: async () =>
    (await import("../../modules/venom-module-brand-studio/web-next/page")).default ?? null,
  google_home_bridge: async () =>
    (await import("../../modules/venom-module-google-home/web-next/page")).default ?? null,
  module_example: async () =>
    (await import("../../modules/venom-module-example/web-next/page")).default ?? null,
};

export async function getOptionalModuleComponent(moduleId: string): Promise<OptionalModuleComponent> {
  const loader = OPTIONAL_MODULE_COMPONENT_LOADERS[moduleId];
  if (!loader) {
    return null;
  }
  try {
    return await loader();
  } catch {
    return null;
  }
}
