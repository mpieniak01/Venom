"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useTranslation } from "@/lib/i18n";
import type { SystemState, PlanRequest } from "@/types/workflow-control";

interface ControlPanelsProps {
  systemState: SystemState | null;
  onApply: (changes: PlanRequest) => Promise<void>;
  isLoading: boolean;
}

export function ControlPanels({
  systemState,
  onApply,
  isLoading,
}: Readonly<ControlPanelsProps>) {
  const t = useTranslation();
  const [decisionStrategy, setDecisionStrategy] = useState("");
  const [intentMode, setIntentMode] = useState("");
  const [kernel, setKernel] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [provider, setProvider] = useState("");

  const handleApply = () => {
    const changes = [];

    if (decisionStrategy && decisionStrategy !== systemState?.decision_strategy) {
      changes.push({
        resource_type: "decision_strategy",
        resource_id: "system",
        action: "update",
        current_value: systemState?.decision_strategy,
        new_value: decisionStrategy,
      });
    }

    if (intentMode && intentMode !== systemState?.intent_mode) {
      changes.push({
        resource_type: "intent_mode",
        resource_id: "system",
        action: "update",
        current_value: systemState?.intent_mode,
        new_value: intentMode,
      });
    }

    if (kernel && kernel !== systemState?.kernel) {
      changes.push({
        resource_type: "kernel",
        resource_id: "system",
        action: "update",
        current_value: systemState?.kernel,
        new_value: kernel,
      });
    }

    if (embeddingModel && embeddingModel !== systemState?.embedding_model) {
      changes.push({
        resource_type: "embedding_model",
        resource_id: "system",
        action: "update",
        current_value: systemState?.embedding_model,
        new_value: embeddingModel,
      });
    }

    if (provider && provider !== systemState?.provider?.active) {
      changes.push({
        resource_type: "provider",
        resource_id: "system",
        action: "update",
        current_value: systemState?.provider?.active,
        new_value: provider,
      });
    }

    if (changes.length > 0) {
      onApply({ changes });
    }
  };

  return (
    <div className="space-y-4">
      {/* Decision & Intent Control */}
      <Card>
        <CardHeader>
          <CardTitle>{t("workflowControl.sections.decision")}</CardTitle>
          <CardDescription>
            {t("workflowControl.sections.decision")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-medium">{t("workflowControl.labels.currentStrategy")}</p>
            <div className="text-sm font-mono p-2 bg-muted rounded">
              {systemState?.decision_strategy || t("workflowControl.common.na")}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="decision-strategy">{t("workflowControl.labels.newStrategy")}</Label>
            <Select
              value={decisionStrategy}
              onValueChange={setDecisionStrategy}
            >
              <SelectTrigger id="decision-strategy">
                <SelectValue placeholder={t("workflowControl.labels.selectStrategy")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="standard">{t("workflowControl.strategies.standard")}</SelectItem>
                <SelectItem value="advanced">{t("workflowControl.strategies.advanced")}</SelectItem>
                <SelectItem value="expert">{t("workflowControl.strategies.expert")}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">{t("workflowControl.labels.currentIntent")}</p>
            <div className="text-sm font-mono p-2 bg-muted rounded">
              {systemState?.intent_mode || t("workflowControl.common.na")}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="intent-mode">{t("workflowControl.labels.newIntent")}</Label>
            <Select value={intentMode} onValueChange={setIntentMode}>
              <SelectTrigger id="intent-mode">
                <SelectValue placeholder={t("workflowControl.labels.selectIntent")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="simple">{t("workflowControl.intentModes.simple")}</SelectItem>
                <SelectItem value="advanced">{t("workflowControl.intentModes.advanced")}</SelectItem>
                <SelectItem value="expert">{t("workflowControl.intentModes.expert")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Kernel & Embedding Control */}
      <Card>
        <CardHeader>
          <CardTitle>{t("workflowControl.sections.kernel")}</CardTitle>
          <CardDescription>
            {t("workflowControl.sections.kernel")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-medium">{t("workflowControl.labels.currentKernel")}</p>
            <div className="text-sm font-mono p-2 bg-muted rounded">
              {systemState?.kernel || t("workflowControl.common.na")}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="kernel">{t("workflowControl.labels.newKernel")}</Label>
            <Select value={kernel} onValueChange={setKernel}>
              <SelectTrigger id="kernel">
                <SelectValue placeholder={t("workflowControl.labels.selectKernel")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="standard">{t("workflowControl.kernelTypes.standard")}</SelectItem>
                <SelectItem value="optimized">{t("workflowControl.kernelTypes.optimized")}</SelectItem>
                <SelectItem value="minimal">{t("workflowControl.kernelTypes.minimal")}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">{t("workflowControl.labels.currentEmbedding")}</p>
            <div className="text-sm font-mono p-2 bg-muted rounded">
              {systemState?.embedding_model || t("workflowControl.common.na")}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="embedding">{t("workflowControl.labels.newEmbedding")}</Label>
            <Select value={embeddingModel} onValueChange={setEmbeddingModel}>
              <SelectTrigger id="embedding">
                <SelectValue placeholder={t("workflowControl.labels.selectEmbedding")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="sentence-transformers">
                  {t("workflowControl.embeddingModels.sentenceTransformers")}
                </SelectItem>
                <SelectItem value="openai-embeddings">
                  {t("workflowControl.embeddingModels.openai")}
                </SelectItem>
                <SelectItem value="google-embeddings">
                  {t("workflowControl.embeddingModels.google")}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Runtime & Provider Control */}
      <Card>
        <CardHeader>
          <CardTitle>{t("workflowControl.sections.runtime")}</CardTitle>
          <CardDescription>
            {t("workflowControl.sections.runtime")}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <p className="text-sm font-medium">{t("workflowControl.labels.runtimeServices")}</p>
            <div className="text-sm font-mono p-2 bg-muted rounded">
              {t("workflowControl.canvas.servicesCount", {
                count: systemState?.runtime?.services?.length || 0,
              })}
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-sm font-medium">{t("workflowControl.labels.currentProvider")}</p>
            <div className="text-sm font-mono p-2 bg-muted rounded">
              {systemState?.provider?.active || t("workflowControl.common.na")}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="provider">{t("workflowControl.labels.newProvider")}</Label>
            <Select value={provider} onValueChange={setProvider}>
              <SelectTrigger id="provider">
                <SelectValue placeholder={t("workflowControl.labels.selectProvider")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ollama">{t("workflowControl.providers.ollama")}</SelectItem>
                <SelectItem value="huggingface">{t("workflowControl.providers.huggingface")}</SelectItem>
                <SelectItem value="openai">{t("workflowControl.providers.openai")}</SelectItem>
                <SelectItem value="google">{t("workflowControl.providers.google")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Apply Button */}
      <Button
        onClick={handleApply}
        disabled={isLoading}
        className="w-full"
      >
        {isLoading ? t("workflowControl.buttons.applying") : t("workflowControl.buttons.planApply")}
      </Button>
    </div>
  );
}
