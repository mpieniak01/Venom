import React from "react";
import { ChevronDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/lib/i18n";
import type { ModelCatalogEntry, ModelInfo, ModelOperation } from "@/lib/types";
import {
    formatNumber,
    getStatusTone,
    getInstalledModelSizeLabel
} from "./models-helpers";

export const SectionHeader = ({
    title,
    subtitle,
    badge,
    actionLabel,
    onAction,
    actionDisabled,
    extra,
    isCollapsed,
    onToggle,
}: {
    title: string;
    subtitle?: string;
    badge?: string;
    actionLabel?: string;
    onAction?: () => void;
    actionDisabled?: boolean;
    extra?: React.ReactNode;
    isCollapsed?: boolean;
    onToggle?: () => void;
}) => {
    const { t } = useLanguage();
    return (
        <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-4">
                <div className="flex flex-col">
                    <p className="text-[10px] uppercase tracking-[0.35em] text-slate-400">{title}</p>
                    {subtitle && <p className="mt-0.5 text-xs text-slate-300">{subtitle}</p>}
                </div>
                <div className="flex items-center gap-3">
                    {extra && <div className="flex items-center gap-2">{extra}</div>}
                    {actionLabel && onAction && (
                        <Button
                            size="sm"
                            variant="outline"
                            className="h-7 rounded-full px-3 text-[10px] uppercase tracking-wider"
                            disabled={actionDisabled}
                            onClick={onAction}
                        >
                            {actionLabel}
                        </Button>
                    )}
                    {badge && <Badge className="text-[10px] py-0.5">{badge}</Badge>}
                    {onToggle && (
                        <button
                            type="button"
                            className="inline-flex h-7 items-center rounded-full border border-white/10 px-3 text-[10px] uppercase tracking-[0.15em] text-slate-400 transition hover:border-white/20 hover:text-white"
                            onClick={onToggle}
                            aria-expanded={!isCollapsed}
                        >
                            <ChevronDown
                                className={cn(
                                    "mr-1.5 h-3 w-3 transition-transform",
                                    isCollapsed ? "rotate-0" : "rotate-180",
                                )}
                            />
                            {isCollapsed ? t("models.actions.expand") : t("models.actions.collapse")}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export const CatalogCard = ({
    model,
    actionLabel,
    onAction,
    pending,
}: {
    model: ModelCatalogEntry;
    actionLabel: string;
    onAction: () => void;
    pending?: boolean;
}) => {
    const { t } = useLanguage();
    return (
        <div className="rounded-3xl box-base p-5 text-white shadow-card">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <p className="text-lg font-semibold">{model.display_name}</p>
                    <p className="text-xs text-slate-400">{model.model_name}</p>
                </div>
                <Badge tone="neutral">{model.runtime}</Badge>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-300">
                <span>{t("models.status.provider")}: {model.provider}</span>
                <span>
                    {t("models.status.size")}: {typeof model.size_gb === "number" ? `${model.size_gb.toFixed(2)} GB` : "—"}
                </span>
                <span>👍 {formatNumber(model.likes)}</span>
                <span>⬇️ {formatNumber(model.downloads)}</span>
            </div>
            {model.tags && model.tags.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                    {model.tags.slice(0, 5).map((tag) => (
                        <Badge key={tag} className="text-[10px]">
                            {tag.length > 30 ? tag.slice(0, 30) + '...' : tag}
                        </Badge>
                    ))}
                </div>
            )}
            <Button
                className="mt-4 rounded-full px-4"
                size="sm"
                variant="secondary"
                disabled={pending}
                onClick={onAction}
            >
                {pending ? t("models.actions.installing") : actionLabel}
            </Button>
        </div>
    );
};

export const InstalledCard = ({
    model,
    onActivate,
    onRemove,
    pendingActivate,
    pendingRemove,
    allowRemoveProviders,
}: {
    model: ModelInfo;
    onActivate: () => void;
    onRemove?: () => void;
    pendingActivate?: boolean;
    pendingRemove?: boolean;
    allowRemoveProviders: Set<string>;
}) => {
    const { t } = useLanguage();
    const providerLabel = model.provider ?? model.source ?? "vllm";
    return (
        <div className="rounded-3xl box-base p-5 text-white shadow-card">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <p className="text-lg font-semibold">{model.name}</p>
                    <p className="text-xs text-slate-400">
                        {getInstalledModelSizeLabel(t, model.size_gb)}{" "}
                        • {providerLabel}
                    </p>
                </div>
                <Badge tone={model.active ? "success" : "neutral"}>
                    {model.active ? t("models.status.active") : t("models.status.installed")}
                </Badge>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
                <Button
                    className="rounded-full px-4"
                    size="sm"
                    variant={model.active ? "secondary" : "outline"}
                    disabled={model.active || pendingActivate}
                    onClick={onActivate}
                >
                    {pendingActivate ? t("models.actions.activating") : t("models.actions.activate")}
                </Button>
                {onRemove && allowRemoveProviders.has(model.provider ?? model.source ?? "") && (
                    <Button
                        className="rounded-full px-4"
                        size="sm"
                        variant="danger"
                        disabled={pendingRemove}
                        onClick={onRemove}
                    >
                        {pendingRemove ? t("models.actions.removing") : t("models.actions.remove")}
                    </Button>
                )}
            </div>
        </div>
    );
};

export const OperationRow = ({ op }: { op: ModelOperation }) => (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl box-base px-4 py-3 text-sm text-slate-200">
        <div>
            <p className="font-medium text-white">{op.model_name}</p>
            <p className="text-xs text-slate-400">
                {op.operation_type} • {op.message || "—"}
            </p>
        </div>
        <div className="flex items-center gap-2">
            {typeof op.progress === "number" && (
                <span className="text-xs text-slate-400">{Math.round(op.progress)}%</span>
            )}
            <Badge tone={getStatusTone(op.status)}>{op.status}</Badge>
        </div>
    </div>
);
