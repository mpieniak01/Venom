"use client";

import { useState, useEffect } from "react";
import { Play, Loader2, RefreshCw, Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LogViewer } from "./log-viewer";
import {
  startTraining,
  listJobs,
  getTrainableModels,
  type TrainingJob,
  type TrainingJobStatus,
  type TrainableModelInfo,
} from "@/lib/academy-api";
import { useLanguage, useTranslation } from "@/lib/i18n";

export function TrainingPanel() {
  const t = useTranslation();
  const { language } = useLanguage();
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [loraRank, setLoraRank] = useState(16);
  const [learningRate, setLearningRate] = useState(0.0002);
  const [numEpochs, setNumEpochs] = useState(3);
  const [batchSize, setBatchSize] = useState(4);
  const [viewingLogs, setViewingLogs] = useState<string | null>(null);
  const [trainableModels, setTrainableModels] = useState<TrainableModelInfo[]>([]);
  const [selectedBaseModel, setSelectedBaseModel] = useState("");
  const [modelsLoading, setModelsLoading] = useState(false);

  useEffect(() => {
    loadJobs();
    loadTrainableModels();
  }, []);

  useEffect(() => {
    // Auto-refresh co 10s tylko gdy są joby running
    if (!jobs.some((j) => j.status === "running")) {
      return;
    }
    const interval = setInterval(() => {
      loadJobs();
    }, 10000);
    return () => clearInterval(interval);
  }, [jobs]);

  async function loadJobs() {
    try {
      const data = await listJobs({ limit: 50 });
      setJobs(data.jobs);
    } catch (err) {
      console.error("Failed to load jobs:", err);
    }
  }

  async function loadTrainableModels() {
    try {
      setModelsLoading(true);
      const models = await getTrainableModels();
      const trainable = models.filter((model) => model.trainable);
      setTrainableModels(trainable);
      setSelectedBaseModel((current) => {
        if (current && trainable.some((model) => model.model_id === current)) {
          return current;
        }
        const recommended = trainable.find((model) => model.recommended);
        return recommended?.model_id ?? trainable[0]?.model_id ?? "";
      });
    } catch (err) {
      console.error("Failed to load trainable models:", err);
      setTrainableModels([]);
      setSelectedBaseModel("");
    } finally {
      setModelsLoading(false);
    }
  }

  async function handleStartTraining() {
    if (!selectedBaseModel) return;
    try {
      setLoading(true);
      await startTraining({
        base_model: selectedBaseModel,
        lora_rank: loraRank,
        learning_rate: learningRate,
        num_epochs: numEpochs,
        batch_size: batchSize,
      });
      await loadJobs();
    } catch (err) {
      console.error("Failed to start training:", err);
    } finally {
      setLoading(false);
    }
  }

  const getStatusColor = (status: TrainingJobStatus) => {
    switch (status) {
      case "queued":
        return "text-amber-300 bg-amber-500/10";
      case "preparing":
        return "text-indigo-300 bg-indigo-500/10";
      case "finished":
        return "text-emerald-400 bg-emerald-500/10";
      case "running":
        return "text-blue-400 bg-blue-500/10";
      case "failed":
        return "text-red-400 bg-red-500/10";
      case "cancelled":
        return "text-orange-300 bg-orange-500/10";
      default:
        return "text-zinc-400 bg-zinc-500/10";
    }
  };

  const getStatusLabel = (status: TrainingJobStatus) => {
    const labels: Record<TrainingJobStatus, string> = {
      queued: t("academy.training.status.queued"),
      preparing: t("academy.training.status.preparing"),
      running: t("academy.training.status.running"),
      finished: t("academy.training.status.finished"),
      failed: t("academy.training.status.failed"),
      cancelled: t("academy.training.status.cancelled"),
    };
    return labels[status];
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">{t("academy.training.title")}</h2>
          <p className="text-sm text-zinc-400">
            {t("academy.training.subtitle")}
          </p>
        </div>
        <Button onClick={loadJobs} variant="outline" size="sm" className="gap-2">
          <RefreshCw className="h-4 w-4" />
          {t("academy.common.refresh")}
        </Button>
      </div>

      {/* Formularz parametrów */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-6">
        <h3 className="mb-4 text-sm font-medium text-zinc-300">{t("academy.training.paramsTitle")}</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="sm:col-span-2 lg:col-span-4">
            <Label htmlFor="base-model" className="text-zinc-300">
              {t("academy.training.baseModel")}
            </Label>
            <select
              id="base-model"
              value={selectedBaseModel}
              onChange={(e) => setSelectedBaseModel(e.target.value)}
              disabled={modelsLoading || trainableModels.length === 0}
              className="mt-2 flex h-10 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {modelsLoading ? (
                <option value="">{t("academy.training.loadingModels")}</option>
              ) : trainableModels.length === 0 ? (
                <option value="">{t("academy.training.noTrainableModels")}</option>
              ) : (
                trainableModels.map((model) => (
                  <option key={model.model_id} value={model.model_id}>
                    {model.label} ({model.provider})
                  </option>
                ))
              )}
            </select>
            <p className="mt-1 text-xs text-zinc-400">{t("academy.training.baseModelHint")}</p>
          </div>
          <div>
            <Label htmlFor="lora-rank" className="text-zinc-300">
              LoRA Rank
            </Label>
            <Input
              id="lora-rank"
              type="number"
              value={loraRank}
              onChange={(e) => setLoraRank(Number.parseInt(e.target.value, 10) || 16)}
              min={4}
              max={64}
              className="mt-2"
            />
            <p className="mt-1 text-xs text-zinc-400">{t("academy.training.loraHint")}</p>
          </div>
          <div>
            <Label htmlFor="learning-rate" className="text-zinc-300">
              {t("academy.training.learningRate")}
            </Label>
            <Input
              id="learning-rate"
              type="number"
              step="0.0001"
              value={learningRate}
              onChange={(e) =>
                setLearningRate(Number.parseFloat(e.target.value) || 0.0002)
              }
              min={0.00001}
              max={0.01}
              className="mt-2"
            />
            <p className="mt-1 text-xs text-zinc-400">0.00001-0.01</p>
          </div>
          <div>
            <Label htmlFor="num-epochs" className="text-zinc-300">
              Epochs
            </Label>
            <Input
              id="num-epochs"
              type="number"
              value={numEpochs}
              onChange={(e) => setNumEpochs(Number.parseInt(e.target.value, 10) || 3)}
              min={1}
              max={20}
              className="mt-2"
            />
            <p className="mt-1 text-xs text-zinc-400">1-20</p>
          </div>
          <div>
            <Label htmlFor="batch-size" className="text-zinc-300">
              Batch Size
            </Label>
            <Input
              id="batch-size"
              type="number"
              value={batchSize}
              onChange={(e) => setBatchSize(Number.parseInt(e.target.value, 10) || 4)}
              min={1}
              max={32}
              className="mt-2"
            />
            <p className="mt-1 text-xs text-zinc-400">{t("academy.training.batchSizeHint")}</p>
          </div>
        </div>

        <Button
          onClick={handleStartTraining}
          disabled={loading || modelsLoading || !selectedBaseModel}
          className="mt-4 gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              {t("academy.training.starting")}
            </>
          ) : (
            <>
              <Play className="h-4 w-4" />
              {t("academy.training.start")}
            </>
          )}
        </Button>
      </div>

      {/* Lista jobów */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-zinc-300">
          {t("academy.training.history", { count: jobs.length })}
        </h3>
        <div className="space-y-2">
          {jobs.length === 0 ? (
            <div className="rounded-xl border border-white/10 bg-white/5 p-8 text-center">
              <p className="text-sm text-zinc-400">{t("academy.training.noJobs")}</p>
            </div>
          ) : (
            jobs.map((job) => (
              <div
                key={job.job_id}
                className="rounded-xl border border-white/10 bg-white/5 p-4"
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-white">{job.job_id}</span>
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${getStatusColor(job.status)}`}>
                        {getStatusLabel(job.status)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-zinc-400">
                      {t("academy.training.startedAt")}: {new Date(job.started_at).toLocaleString(language)}
                    </p>
                    {job.finished_at && (
                      <p className="text-xs text-zinc-400">
                        {t("academy.training.finishedAt")}: {new Date(job.finished_at).toLocaleString(language)}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <p className="text-xs text-zinc-400">{t("academy.training.epochs")}: {job.parameters.num_epochs}</p>
                      <p className="text-xs text-zinc-400">{t("academy.training.lora")}: {job.parameters.lora_rank}</p>
                    </div>
                    <Button
                      onClick={() => setViewingLogs(job.job_id)}
                      variant="outline"
                      size="sm"
                      className="gap-2"
                    >
                      <Terminal className="h-4 w-4" />
                      {t("academy.training.logs")}
                    </Button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Log Viewer */}
      {viewingLogs && (
        <div className="mt-6">
          <LogViewer
            jobId={viewingLogs}
            onClose={() => setViewingLogs(null)}
          />
        </div>
      )}
    </div>
  );
}
