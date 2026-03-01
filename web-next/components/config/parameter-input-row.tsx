"use client";

import { Eye, EyeOff } from "lucide-react";
import { IconButton } from "@/components/ui/icon-button";
import { SelectMenu } from "@/components/ui/select-menu";

export function ParameterInputRow(input: Readonly<{
  t: (key: string) => string;
  keyName: string;
  value: string;
  valueSource: "env" | "default";
  secret: boolean;
  showValue: boolean;
  onToggleSecret: () => void;
  onChange: (value: string) => void;
}>) {
  const {
    t,
    keyName,
    value,
    valueSource,
    secret,
    showValue,
    onToggleSecret,
    onChange,
  } = input;

  const isBooleanKey = (key: string, val: string) => {
    const k = key.toUpperCase();
    const v = val.toLowerCase();
    if (v === "true" || v === "false") return true;
    return (
      k.startsWith("ENABLE_") ||
      k.startsWith("IS_") ||
      k.startsWith("HAS_") ||
      k.startsWith("USE_") ||
      k.endsWith("_ENABLED")
    );
  };
  const isBool = isBooleanKey(keyName, value);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-zinc-300">
          {keyName.replaceAll(/[_-]+/g, " ").replaceAll(/\b\w/g, (m) => m.toUpperCase())}
        </label>
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${valueSource === "default" ? "bg-amber-500/20 text-amber-300" : "bg-emerald-500/20 text-emerald-300"}`}
          >
            {valueSource === "default"
              ? t("config.parameters.valueSource.default")
              : t("config.parameters.valueSource.env")}
          </span>
          {secret ? (
            <IconButton
              label={
                showValue
                  ? t("config.parameters.sections.secrets.hide")
                  : t("config.parameters.sections.secrets.show")
              }
              icon={showValue ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              variant="ghost"
              size="xs"
              className="text-zinc-500 hover:text-zinc-300"
              onClick={onToggleSecret}
            />
          ) : null}
        </div>
      </div>
      {isBool ? (
        <SelectMenu
          value={value.toLowerCase() === "true" ? "true" : "false"}
          options={[
            { value: "true", label: "True" },
            { value: "false", label: "False" },
          ]}
          onChange={(newValue) => onChange(newValue)}
          buttonClassName="w-full justify-between rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white hover:bg-white/5 hover:border-white/20 transition-colors"
          menuClassName="w-full"
        />
      ) : (
        <input
          type={showValue ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-sm text-white outline-none focus:border-emerald-400 focus:ring-0"
        />
      )}
      {valueSource === "default" ? (
        <p className="text-xs text-amber-200/80">{t("config.parameters.effectiveConfigHint")}</p>
      ) : null}
    </div>
  );
}
