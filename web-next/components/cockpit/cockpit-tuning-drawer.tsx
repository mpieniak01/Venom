"use client";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { DynamicParameterForm, type GenerationSchema } from "@/components/ui/dynamic-parameter-form";
import type { GenerationParams } from "@/lib/types";

type CockpitTuningDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  loadingSchema: boolean;
  modelSchema: GenerationSchema | null;
  generationParams: GenerationParams | null;
  onChangeGenerationParams: (values: Record<string, unknown>) => void;
  onResetGenerationParams: () => void;
  tuningSaving: boolean;
  onApply: () => void;
};

export function CockpitTuningDrawer({
  open,
  onOpenChange,
  loadingSchema,
  modelSchema,
  generationParams,
  onChangeGenerationParams,
  onResetGenerationParams,
  tuningSaving,
  onApply,
}: CockpitTuningDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-md overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Parametry Generacji</SheetTitle>
          <SheetDescription>
            Dostosuj parametry modelu, takie jak temperatura, max_tokens, etc.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-6">
          {loadingSchema && (
            <div className="flex items-center justify-center py-12">
              <span className="text-sm text-zinc-400">Ładuję parametry…</span>
            </div>
          )}
          {!loadingSchema && !modelSchema && (
            <p className="text-sm text-zinc-400">
              Brak schematu parametrów dla aktywnego modelu.
            </p>
          )}
          {!loadingSchema && modelSchema && (
            <>
              <DynamicParameterForm
                schema={modelSchema}
                values={generationParams || undefined}
                onChange={(values) => onChangeGenerationParams(values)}
                onReset={onResetGenerationParams}
              />
              <div className="mt-4 flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  className="border-white/20 bg-white/5 text-white hover:bg-white/10"
                  disabled={tuningSaving}
                  onClick={onApply}
                >
                  {tuningSaving ? "Zapisuję..." : "Zastosuj"}
                </Button>
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
