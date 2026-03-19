"use client";

import { useState } from "react";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { AlertCircle, ChevronDown, AlertTriangle, Zap, Package, Edit2 } from "lucide-react";
import type { OperatorConfigField } from "@/types/workflow-control";

interface ConfigFieldsEditorProps {
  configFields: OperatorConfigField[];
  onUpdateField: (field: OperatorConfigField, value: unknown) => void;
}

function toDisplayString(value: unknown, emptyFallback = "(empty)"): string {
  if (value == null || value === "") {
    return emptyFallback;
  }
  if (typeof value === "string") {
    return value;
  }
  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  ) {
    return String(value);
  }
  if (typeof value === "symbol" || typeof value === "function") {
    return "[unsupported value]";
  }
  try {
    const serialized = JSON.stringify(value);
    if (typeof serialized === "string") {
      return serialized;
    }
    return "[unsupported value]";
  } catch {
    return "[unsupported value]";
  }
}

function ConfigFieldCard({
  field,
  isExpanded,
  onToggle,
  onUpdateValue,
  isDirty,
  draftValue,
}: Readonly<{
  field: OperatorConfigField;
  isExpanded: boolean;
  onToggle: () => void;
  onUpdateValue: (value: unknown) => void;
  isDirty: boolean;
  draftValue?: unknown;
}>) {
  const hasOptions = (field.options?.length ?? 0) > 0;
  const options = field.options ?? [];
  const hasDraftValue = draftValue !== undefined;
  const displayValue = hasDraftValue ? draftValue : field.value;
  const displayValueText = toDisplayString(displayValue);
  const effectiveValueText = toDisplayString(field.effective_value);
  const readOnly = field.editable === false;
  const editable = !readOnly;
  const canUseOptionPills = hasOptions && options.length <= 8;

  return (
    <div className="overflow-hidden rounded-[20px] border border-white/10 bg-slate-950/75 transition-colors hover:border-white/20">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 transition-colors hover:bg-slate-900/80"
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <Edit2 className="h-4 w-4 shrink-0 text-cyan-300" />
          <div className="text-left min-w-0">
            <div className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-200">{field.key}</div>
            <div className="truncate font-mono text-[11px] text-slate-500">
              {field.entity_id}
              {field.field && `.${field.field}`}
            </div>
          </div>
          <div className="ml-auto flex-shrink-0 flex items-center gap-2">
            {isDirty && <div className="w-2 h-2 rounded-full bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.6)]" />}
            {field.restart_required && <Zap className="w-3.5 h-3.5 text-orange-500" />}
          </div>
        </div>
        <ChevronDown className={`h-4 w-4 text-slate-500 transition-transform ${isExpanded ? "rotate-180" : ""}`} />
      </button>

      {isExpanded && (
        <div className="space-y-4 border-t border-white/10 bg-slate-950/90 px-4 py-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor={`current-${field.key}`} className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                Current Value
              </Label>
              <div id={`current-${field.key}`} className="mt-1.5 break-all rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2 text-xs font-mono text-slate-300">
                {displayValueText}
              </div>
            </div>
            {field.effective_value !== field.value && (
              <div>
                <Label htmlFor={`effective-${field.key}`} className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                  Effective Value
                </Label>
                <div id={`effective-${field.key}`} className="mt-1.5 break-all rounded-xl border border-cyan-400/20 bg-cyan-500/10 px-3 py-2 text-xs font-mono text-cyan-200">
                  {effectiveValueText}
                </div>
              </div>
            )}
          </div>

          <div>
            <Label htmlFor={`cfg-${field.key}`} className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
              Set Value
            </Label>
            {canUseOptionPills ? (
              <div className="mb-3 flex flex-wrap gap-2">
                {options.map((opt) => {
                  const isActive = String(displayValue ?? "") === opt;
                  return (
                    <button
                      key={opt}
                      type="button"
                      onClick={editable ? () => onUpdateValue(opt) : undefined}
                      disabled={readOnly}
                      className={[
                        "rounded-full border px-3 py-1.5 text-xs transition",
                        isActive
                          ? "border-sky-400/30 bg-sky-500/10 text-sky-200"
                          : "border-white/10 bg-slate-950/70 text-slate-400 hover:border-white/20 hover:text-slate-200",
                        readOnly ? "cursor-not-allowed opacity-60" : "",
                      ].join(" ")}
                    >
                      {opt}
                    </button>
                  );
                })}
              </div>
            ) : null}
            {hasOptions ? (
              <Select
                value={toDisplayString(displayValue, "")}
                onValueChange={editable ? (val) => onUpdateValue(val) : undefined}
                disabled={readOnly}
                aria-disabled={readOnly}
              >
                <SelectTrigger id={`cfg-${field.key}`} className="border-white/10 bg-slate-900/80 text-slate-100 focus:ring-cyan-500/30">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-white/10 bg-slate-950 text-slate-100">
                  {options.map((opt) => (
                    <SelectItem key={opt} value={opt} className="focus:bg-cyan-500/15">
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                id={`cfg-${field.key}`}
                type="text"
                value={toDisplayString(displayValue, "")}
                onChange={editable ? (e) => onUpdateValue(e.target.value) : undefined}
                disabled={readOnly}
                aria-disabled={readOnly}
                className="border-white/10 bg-slate-900/80 text-slate-100 placeholder-slate-600 focus:ring-cyan-500/30"
                placeholder={`Enter value for ${field.key}`}
              />
            )}
          </div>

          {field.restart_required && (
            <div className="flex items-start gap-2 rounded-2xl border border-orange-400/20 bg-orange-500/10 p-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-orange-300" />
              <div>
                <p className="text-xs font-semibold text-orange-200">Requires Restart</p>
                <p className="mt-0.5 text-[11px] text-orange-100/70">Service restart required to apply this change.</p>
              </div>
            </div>
          )}

          {(field.affected_services?.length ?? 0) > 0 && (
            <div className="flex items-start gap-2 rounded-2xl border border-violet-400/20 bg-violet-500/10 p-3">
              <Package className="mt-0.5 h-4 w-4 shrink-0 text-violet-300" />
              <div className="min-w-0">
                <p className="text-xs font-semibold text-violet-200">Affected Services</p>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {(field.affected_services ?? []).map((svc) => (
                    <span key={svc} className="rounded-full border border-white/10 bg-slate-950/70 px-2 py-1 text-[10px] font-mono text-slate-300">
                      {svc}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {field.editable === false && (
            <div className="flex items-start gap-2 rounded-2xl border border-white/10 bg-slate-900/80 p-3">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
              <p className="text-[11px] text-slate-400">This field is read-only.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ConfigFieldsEditor({
  configFields,
  onUpdateField,
}: Readonly<ConfigFieldsEditorProps>) {
  const [expandedFields, setExpandedFields] = useState<Set<string>>(new Set());
  const [editingValues, setEditingValues] = useState<Record<string, unknown>>({});

  if (configFields.length === 0) {
    return null;
  }

  const toggleField = (key: string) => {
    setExpandedFields((prev) =>
      prev.has(key) ? new Set([...prev].filter((k) => k !== key)) : new Set([...prev, key])
    );
  };

  const handleFieldUpdate = (field: OperatorConfigField, value: unknown) => {
    setEditingValues((prev) => ({ ...prev, [field.key]: value }));
    onUpdateField(field, value);
  };

  const editableFields = configFields.filter((f) => f.editable !== false);
  const readOnlyFields = configFields.filter((f) => f.editable === false);

  return (
    <div className="rounded-[24px] border border-sky-400/20 bg-slate-900/80 p-4 shadow-[0_12px_40px_rgba(2,6,23,0.28)]">
      <div className="mb-4 flex items-center gap-2 border-b border-white/10 pb-3">
        <Edit2 className="h-4 w-4 text-sky-300" />
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.24em] text-sky-300">System Configuration</h3>
      </div>

      <div className="space-y-4">
        {editableFields.length > 0 && (
          <div className="space-y-2">
            <h4 className="px-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-sky-300">Editable Fields ({editableFields.length})</h4>
            <div className="space-y-2">
              {editableFields.map((field) => (
                <ConfigFieldCard
                  key={field.key}
                  field={field}
                  isExpanded={expandedFields.has(field.key)}
                  onToggle={() => toggleField(field.key)}
                  onUpdateValue={(value) => handleFieldUpdate(field, value)}
                  isDirty={editingValues[field.key] !== undefined}
                  draftValue={editingValues[field.key]}
                />
              ))}
            </div>
          </div>
        )}

        {readOnlyFields.length > 0 && (
          <div className="space-y-2">
            <h4 className="px-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">Read-Only Fields ({readOnlyFields.length})</h4>
            <div className="space-y-2">
              {readOnlyFields.map((field) => (
                <ConfigFieldCard
                  key={field.key}
                  field={field}
                  isExpanded={expandedFields.has(field.key)}
                  onToggle={() => toggleField(field.key)}
                  onUpdateValue={() => undefined}
                  isDirty={false}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
