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
}: ControlPanelsProps) {
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
          <CardTitle>Decision & Intent Control</CardTitle>
          <CardDescription>
            Configure decision strategy and intent mode
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Current Strategy</Label>
            <div className="text-sm font-mono p-2 bg-muted rounded">
              {systemState?.decision_strategy || "N/A"}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="decision-strategy">New Strategy</Label>
            <Select
              value={decisionStrategy}
              onValueChange={setDecisionStrategy}
            >
              <SelectTrigger id="decision-strategy">
                <SelectValue placeholder="Select strategy" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="standard">Standard</SelectItem>
                <SelectItem value="advanced">Advanced</SelectItem>
                <SelectItem value="expert">Expert</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Current Intent Mode</Label>
            <div className="text-sm font-mono p-2 bg-muted rounded">
              {systemState?.intent_mode || "N/A"}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="intent-mode">New Intent Mode</Label>
            <Select value={intentMode} onValueChange={setIntentMode}>
              <SelectTrigger id="intent-mode">
                <SelectValue placeholder="Select mode" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="simple">Simple</SelectItem>
                <SelectItem value="advanced">Advanced</SelectItem>
                <SelectItem value="expert">Expert</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Kernel & Embedding Control */}
      <Card>
        <CardHeader>
          <CardTitle>Kernel & Embedding Control</CardTitle>
          <CardDescription>
            Configure kernel type and embedding model
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Current Kernel</Label>
            <div className="text-sm font-mono p-2 bg-muted rounded">
              {systemState?.kernel || "N/A"}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="kernel">New Kernel</Label>
            <Select value={kernel} onValueChange={setKernel}>
              <SelectTrigger id="kernel">
                <SelectValue placeholder="Select kernel" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="standard">Standard</SelectItem>
                <SelectItem value="optimized">Optimized</SelectItem>
                <SelectItem value="minimal">Minimal</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Current Embedding Model</Label>
            <div className="text-sm font-mono p-2 bg-muted rounded">
              {systemState?.embedding_model || "N/A"}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="embedding">New Embedding Model</Label>
            <Select value={embeddingModel} onValueChange={setEmbeddingModel}>
              <SelectTrigger id="embedding">
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="sentence-transformers">
                  Sentence Transformers
                </SelectItem>
                <SelectItem value="openai-embeddings">
                  OpenAI Embeddings
                </SelectItem>
                <SelectItem value="google-embeddings">
                  Google Embeddings
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Runtime & Provider Control */}
      <Card>
        <CardHeader>
          <CardTitle>Runtime & Provider Control</CardTitle>
          <CardDescription>
            Configure runtime and provider settings
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Runtime Status</Label>
            <div className="text-sm font-mono p-2 bg-muted rounded">
              {systemState?.runtime?.services?.length || 0} services running
            </div>
          </div>

          <div className="space-y-2">
            <Label>Current Provider</Label>
            <div className="text-sm font-mono p-2 bg-muted rounded">
              {systemState?.provider?.active || "N/A"}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="provider">New Provider</Label>
            <Select value={provider} onValueChange={setProvider}>
              <SelectTrigger id="provider">
                <SelectValue placeholder="Select provider" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ollama">Ollama</SelectItem>
                <SelectItem value="huggingface">HuggingFace</SelectItem>
                <SelectItem value="openai">OpenAI</SelectItem>
                <SelectItem value="google">Google</SelectItem>
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
        size="lg"
      >
        {isLoading ? "Applying..." : "Plan & Apply Changes"}
      </Button>
    </div>
  );
}
