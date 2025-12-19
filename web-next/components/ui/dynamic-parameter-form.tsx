"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";

/**
 * Schema parametru generacji z backendu
 */
export type GenerationParameterSchema = {
  type: "float" | "int" | "bool" | "list" | "enum";
  default: any;
  min?: number;
  max?: number;
  desc?: string;
  options?: any[];
};

/**
 * Słownik schematów parametrów
 */
export type GenerationSchema = Record<string, GenerationParameterSchema>;

/**
 * Props dla DynamicParameterForm
 */
type DynamicParameterFormProps = {
  schema: GenerationSchema;
  values?: Record<string, any>;
  onChange?: (values: Record<string, any>) => void;
  onReset?: () => void;
};

/**
 * Komponent renderujący pojedynczy parametr
 */
function ParameterControl({
  name,
  schema,
  value,
  onChange,
}: {
  name: string;
  schema: GenerationParameterSchema;
  value: any;
  onChange: (value: any) => void;
}) {
  const { type, min, max, desc, options } = schema;

  // Float/Int - Slider + Input numeryczny
  if (type === "float" || type === "int") {
    const step = type === "float" ? 0.1 : 1;
    const numValue = Number(value);

    const handleNumericChange = (rawValue: string) => {
      const parsed = type === "float" ? parseFloat(rawValue) : parseInt(rawValue, 10);
      // Walidacja NaN i zakresu
      if (!isNaN(parsed)) {
        const clamped = Math.max(min ?? -Infinity, Math.min(max ?? Infinity, parsed));
        onChange(clamped);
      }
    };

    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-zinc-200">{name}</label>
          <input
            type="number"
            value={numValue}
            onChange={(e) => handleNumericChange(e.target.value)}
            step={step}
            min={min}
            max={max}
            className="w-20 rounded border border-white/20 bg-white/5 px-2 py-1 text-right text-sm text-white focus:border-violet-500 focus:outline-none"
          />
        </div>
        <input
          type="range"
          value={numValue}
          onChange={(e) => handleNumericChange(e.target.value)}
          step={step}
          min={min}
          max={max}
          className="h-2 w-full cursor-pointer appearance-none rounded-lg bg-white/10 accent-violet-500"
        />
        {desc && <p className="text-xs text-zinc-400">{desc}</p>}
      </div>
    );
  }

  // Bool - Przełącznik (Toggle/Switch)
  if (type === "bool") {
    return (
      <div className="flex items-center justify-between">
        <div>
          <label className="text-sm font-medium text-zinc-200">{name}</label>
          {desc && <p className="text-xs text-zinc-400">{desc}</p>}
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={value}
          onClick={() => onChange(!value)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-violet-500 focus:ring-offset-2 focus:ring-offset-zinc-900 ${
            value ? "bg-violet-600" : "bg-white/20"
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              value ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
      </div>
    );
  }

  // List/Enum - Dropdown (Select)
  if (type === "list" || type === "enum") {
    // Walidacja options - jeśli brak lub puste, pokaż komunikat
    if (!options || options.length === 0) {
      return (
        <div className="space-y-2">
          <label className="text-sm font-medium text-zinc-200">{name}</label>
          <p className="text-sm text-amber-400">Brak dostępnych opcji dla tego parametru</p>
          {desc && <p className="text-xs text-zinc-400">{desc}</p>}
        </div>
      );
    }

    return (
      <div className="space-y-2">
        <label className="text-sm font-medium text-zinc-200">{name}</label>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded border border-white/20 bg-white/5 px-3 py-2 text-sm text-white focus:border-violet-500 focus:outline-none"
        >
          {options.map((option) => (
            <option key={option} value={option} className="bg-zinc-800">
              {option}
            </option>
          ))}
        </select>
        {desc && <p className="text-xs text-zinc-400">{desc}</p>}
      </div>
    );
  }

  return null;
}

/**
 * DynamicParameterForm - Dynamiczny formularz parametrów modelu
 *
 * Renderuje interfejs użytkownika na podstawie JSON Schema z backendu.
 * Obsługuje różne typy parametrów:
 * - float/int → Suwak + Input numeryczny
 * - bool → Przełącznik (Switch/Toggle)
 * - list/enum → Dropdown (Select)
 */
export function DynamicParameterForm({
  schema,
  values: initialValues,
  onChange,
  onReset,
}: DynamicParameterFormProps) {
  // Stan lokalny z wartościami parametrów
  const [values, setValues] = useState<Record<string, any>>(() => {
    const defaults: Record<string, any> = {};
    Object.entries(schema).forEach(([key, paramSchema]) => {
      defaults[key] = paramSchema.default;
    });
    return initialValues || defaults;
  });

  // Aktualizuj wartości gdy initialValues się zmieni
  useEffect(() => {
    if (initialValues) {
      setValues(initialValues);
    }
  }, [initialValues]);

  // Wywołaj onChange gdy wartości się zmienią
  // Używamy ref aby uniknąć problemów z zależnościami i potencjalnych pętli
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (onChangeRef.current) {
      onChangeRef.current(values);
    }
  }, [values]);

  const handleValueChange = (name: string, value: any) => {
    setValues((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleReset = () => {
    const defaults: Record<string, any> = {};
    Object.entries(schema).forEach(([key, paramSchema]) => {
      defaults[key] = paramSchema.default;
    });
    setValues(defaults);
    if (onReset) {
      onReset();
    }
  };

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        {Object.entries(schema).map(([name, paramSchema]) => (
          <ParameterControl
            key={name}
            name={name}
            schema={paramSchema}
            value={values[name]}
            onChange={(value) => handleValueChange(name, value)}
          />
        ))}
      </div>
      <div className="flex justify-end gap-2 border-t border-white/10 pt-4">
        <Button
          type="button"
          onClick={handleReset}
          className="border-white/20 bg-white/5 text-white hover:bg-white/10"
        >
          Resetuj
        </Button>
      </div>
    </div>
  );
}
