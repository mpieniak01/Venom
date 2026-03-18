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

  return (
    <div className="border border-slate-700 rounded-lg bg-slate-900/40 overflow-hidden hover:border-slate-600 transition-colors">
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-slate-800/50 transition-colors"
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <Edit2 className="w-4 h-4 text-cyan-400 flex-shrink-0" />
          <div className="text-left min-w-0">
            <div className="text-xs font-bold text-slate-300 uppercase tracking-wider">{field.key}</div>
            <div className="text-[11px] text-slate-500 font-mono truncate">
              {field.entity_id}
              {field.field && `.${field.field}`}
            </div>
          </div>
          <div className="ml-auto flex-shrink-0 flex items-center gap-2">
            {isDirty && <div className="w-2 h-2 rounded-full bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.6)]" />}
            {field.restart_required && <Zap className="w-3.5 h-3.5 text-orange-500" />}
          </div>
        </div>
        <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${isExpanded ? "rotate-180" : ""}`} />
      </button>

      {isExpanded && (
        <div className="border-t border-slate-700 bg-slate-950/40 px-4 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor={`current-${field.key}`} className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                Current Value
              </Label>
              <div id={`current-${field.key}`} className="mt-1.5 text-xs font-mono bg-slate-800/50 border border-slate-700 rounded px-2 py-1.5 text-slate-300 break-all">
                {displayValueText}
              </div>
            </div>
            {field.effective_value !== field.value && (
              <div>
                <Label htmlFor={`effective-${field.key}`} className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
                  Effective Value
                </Label>
                <div id={`effective-${field.key}`} className="mt-1.5 text-xs font-mono bg-slate-800/50 border border-slate-700 rounded px-2 py-1.5 text-cyan-300 break-all">
                  {effectiveValueText}
                </div>
              </div>
            )}
          </div>

          <div>
            <Label htmlFor={`cfg-${field.key}`} className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1.5 block">
              Set Value
            </Label>
            {hasOptions ? (
              <Select
                value={toDisplayString(displayValue, "")}
                onValueChange={editable ? (val) => onUpdateValue(val) : undefined}
                disabled={readOnly}
                aria-disabled={readOnly}
              >
                <SelectTrigger id={`cfg-${field.key}`} className="bg-slate-800/60 border-cyan-500/30 text-cyan-100 focus:ring-cyan-500/50">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-slate-900 border-cyan-500/30 text-cyan-100">
                  {options.map((opt) => (
                    <SelectItem key={opt} value={opt} className="focus:bg-cyan-500/20">
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
                className="bg-slate-800/60 border-cyan-500/30 text-cyan-100 placeholder-slate-600 focus:ring-cyan-500/50"
                placeholder={`Enter value for ${field.key}`}
              />
            )}
          </div>

          {field.restart_required && (
            <div className="p-2.5 rounded-lg bg-orange-500/10 border border-orange-500/30 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-orange-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-bold text-orange-300">Requires Restart</p>
                <p className="text-[11px] text-orange-200/70 mt-0.5">Service restart required to apply this change.</p>
              </div>
            </div>
          )}

          {(field.affected_services?.length ?? 0) > 0 && (
            <div className="p-2.5 rounded-lg bg-purple-500/10 border border-purple-500/30 flex items-start gap-2">
              <Package className="w-4 h-4 text-purple-400 flex-shrink-0 mt-0.5" />
              <div className="min-w-0">
                <p className="text-xs font-bold text-purple-300">Affected Services</p>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {(field.affected_services ?? []).map((svc) => (
                    <span key={svc} className="text-[10px] px-2 py-1 rounded bg-purple-500/20 text-purple-200 border border-purple-500/40 font-mono">
                      {svc}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {field.editable === false && (
            <div className="p-2.5 rounded-lg bg-slate-700/50 border border-slate-600 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />
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
    <div className="p-4 rounded-2xl border border-cyan-500/20 bg-cyan-500/5 shadow-[0_4px_25px_rgba(6,182,212,0.05)]">
      <div className="flex items-center gap-2 mb-3 border-b border-cyan-500/20 pb-2">
        <Edit2 className="w-4 h-4 text-cyan-400" />
        <h3 className="text-[10px] font-bold uppercase tracking-widest text-cyan-400">System Configuration</h3>
      </div>

      <div className="space-y-4">
        {editableFields.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-[10px] font-bold text-cyan-400 uppercase tracking-widest px-1">Editable Fields ({editableFields.length})</h4>
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
            <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest px-1">Read-Only Fields ({readOnlyFields.length})</h4>
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
