import type { AdapterAuditItem } from "./academy-api";
import type { SelectMenuOption } from "@/components/ui/select-menu";

export type CockpitAdapterCatalogEntry = {
  adapter_id: string;
  adapter_path: string;
  base_model: string;
  canonical_base_model_id?: string;
  is_active: boolean;
  compatible_runtimes?: string[];
};

type BuildCockpitAdapterOptionsParams = {
  adapters: CockpitAdapterCatalogEntry[];
  auditById: Record<string, AdapterAuditItem>;
  adapterDeploySupported: boolean;
  baseOptionValue: string;
  baseOptionLabel: string;
  compatibleLabel: string;
  blockedLabel: string;
  unknownStatusLabel: string;
};

export function isBlockedCockpitAdapterAudit(
  audit: AdapterAuditItem | null | undefined,
): boolean {
  // Runtime/base model mismatch is informational in Cockpit adapter flow:
  // selected adapter is the deploy target and can override currently selected
  // base model. Only unknown/incomplete metadata should hard-block selection.
  return audit?.category === "blocked_unknown_base";
}

export function buildCockpitAdapterOptions({
  adapters,
  auditById,
  adapterDeploySupported,
  baseOptionValue,
  baseOptionLabel,
  compatibleLabel,
  blockedLabel,
  unknownStatusLabel,
}: BuildCockpitAdapterOptionsParams): SelectMenuOption[] {
  const baseOption: SelectMenuOption = {
    value: baseOptionValue,
    label: baseOptionLabel,
  };
  if (!adapterDeploySupported) {
    return [baseOption];
  }
  return [
    baseOption,
    ...adapters.map((adapter) => {
      const audit = auditById[adapter.adapter_id];
      const blocked = isBlockedCockpitAdapterAudit(audit);
      let statusLabel = unknownStatusLabel;
      if (audit) {
        statusLabel = blocked ? blockedLabel : compatibleLabel;
      }
      const statusMessage = audit?.message ? ` - ${audit.message}` : "";
      return {
        value: adapter.adapter_id,
        label: adapter.adapter_id,
        description: `${adapter.base_model} | ${statusLabel}${statusMessage}`,
        disabled: blocked,
      };
    }),
  ];
}
