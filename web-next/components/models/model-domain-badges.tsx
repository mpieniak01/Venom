/**
 * Model Domain Badge Components v2
 *
 * Visual badges for displaying model domain classifications:
 * - Source Type (local-runtime, cloud-api, integrator-catalog)
 * - Model Role (llm-engine, intent-embedding)
 * - Trainability Status (trainable, not-trainable)
 */

import React from "react";
import type {
  ModelSourceType,
  ModelRole,
  ModelTrainabilityStatus,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface BadgeProps {
  className?: string;
}

interface SourceTypeBadgeProps extends Readonly<BadgeProps> {
  sourceType: ModelSourceType;
  label: string;
}

interface ModelRoleBadgeProps extends Readonly<BadgeProps> {
  role: ModelRole;
  label: string;
}

interface TrainabilityBadgeProps extends Readonly<BadgeProps> {
  status: ModelTrainabilityStatus;
  label: string;
  reason?: string | null;
  showTooltip?: boolean;
}

/**
 * Source Type Badge
 */
export function SourceTypeBadge({ sourceType, label, className }: Readonly<SourceTypeBadgeProps>) {
  const styles = {
    "local-runtime": "bg-blue-500/10 text-blue-300 border-blue-500/30",
    "cloud-api": "bg-purple-500/10 text-purple-300 border-purple-500/30",
    "integrator-catalog": "bg-amber-500/10 text-amber-300 border-amber-500/30",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        styles[sourceType],
        className
      )}
    >
      {label}
    </span>
  );
}

/**
 * Model Role Badge
 */
export function ModelRoleBadge({ role, label, className }: Readonly<ModelRoleBadgeProps>) {
  const styles = {
    "llm-engine": "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
    "intent-embedding": "bg-cyan-500/10 text-cyan-300 border-cyan-500/30",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        styles[role],
        className
      )}
    >
      {label}
    </span>
  );
}

/**
 * Trainability Badge
 */
export function TrainabilityBadge({
  status,
  label,
  reason,
  showTooltip = true,
  className,
}: Readonly<TrainabilityBadgeProps>) {
  const styles = {
    trainable: "bg-green-500/10 text-green-300 border-green-500/30",
    "not-trainable": "bg-zinc-500/10 text-zinc-400 border-zinc-500/30",
  };

  const badge = (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        styles[status],
        className
      )}
      title={showTooltip && reason ? reason : undefined}
    >
      {label}
    </span>
  );

  return badge;
}

/**
 * Combined Domain Badges Component
 */
interface DomainBadgesProps {
  sourceType: ModelSourceType;
  sourceTypeLabel: string;
  modelRole: ModelRole;
  modelRoleLabel: string;
  trainabilityStatus: ModelTrainabilityStatus;
  trainabilityLabel: string;
  trainabilityReason?: string | null;
  className?: string;
}

export function DomainBadges({
  sourceType,
  sourceTypeLabel,
  modelRole,
  modelRoleLabel,
  trainabilityStatus,
  trainabilityLabel,
  trainabilityReason,
  className,
}: Readonly<DomainBadgesProps>) {
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      <SourceTypeBadge sourceType={sourceType} label={sourceTypeLabel} />
      <ModelRoleBadge role={modelRole} label={modelRoleLabel} />
      <TrainabilityBadge
        status={trainabilityStatus}
        label={trainabilityLabel}
        reason={trainabilityReason}
      />
    </div>
  );
}
