import "server-only";

import type { ComponentType } from "react";
import { OPTIONAL_MODULE_COMPONENT_LOADERS } from "@/lib/generated/optional-module-components.generated.server";

type OptionalModuleComponent = ComponentType | null;

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
