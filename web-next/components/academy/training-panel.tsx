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
  type AcademyStatus,
  type TrainingJob,
} from "@/lib/academy-api";

interface TrainingPanelProps {
  status: AcademyStatus;
}

export function TrainingPanel({ status }: TrainingPanelProps) {
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [loraRank, setLoraRank] = useState(16);
  const [learningRate, setLearningRate] = useState(0.0002);
  const [numEpochs, setNumEpochs] = useState(3);
  const [batchSize, setBatchSize] = useState(4);
  const [viewingLogs, setViewingLogs] = useState<string | null>(null);

  useEffect(() => {
    loadJobs();
    // Auto-refresh co 10s jeśli są running jobs
    const interval = setInterval(() => {
      if (jobs.some(j => j.status === "running")) {
        loadJobs();
      }
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

  async function handleStartTraining() {
    try {
      setLoading(true);
      await startTraining({
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

  const getStatusColor = (status: string) => {
    switch (status) {
      case "finished":
        return "text-emerald-400 bg-emerald-500/10";
      case "running":
        return "text-blue-400 bg-blue-500/10";
      case "failed":
        return "text-red-400 bg-red-500/10";
      default:
        return "text-zinc-400 bg-zinc-500/10";
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Trening Modelu</h2>
          <p className="text-sm text-zinc-400">
            Uruchom LoRA fine-tuning z własnymi parametrami
          </p>
        </div>
        <Button onClick={loadJobs} variant="outline" size="sm" className="gap-2">
          <RefreshCw className="h-4 w-4" />
          Odśwież
        </Button>
      </div>

      {/* Formularz parametrów */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-6">
        <h3 className="mb-4 text-sm font-medium text-zinc-300">Parametry Treningu</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <Label htmlFor="lora-rank" className="text-zinc-300">
              LoRA Rank
            </Label>
            <Input
              id="lora-rank"
              type="number"
              value={loraRank}
              onChange={(e) => setLoraRank(parseInt(e.target.value) || 16)}
              min={4}
              max={64}
              className="mt-2"
            />
            <p className="mt-1 text-xs text-zinc-400">4-64 (wyższy = więcej parametrów)</p>
          </div>
          <div>
            <Label htmlFor="learning-rate" className="text-zinc-300">
              Learning Rate
            </Label>
            <Input
              id="learning-rate"
              type="number"
              step="0.0001"
              value={learningRate}
              onChange={(e) => setLearningRate(parseFloat(e.target.value) || 0.0002)}
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
              onChange={(e) => setNumEpochs(parseInt(e.target.value) || 3)}
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
              onChange={(e) => setBatchSize(parseInt(e.target.value) || 4)}
              min={1}
              max={32}
              className="mt-2"
            />
            <p className="mt-1 text-xs text-zinc-400">1-32 (mniejszy = mniej VRAM)</p>
          </div>
        </div>

        <Button
          onClick={handleStartTraining}
          disabled={loading}
          className="mt-4 gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Uruchamianie...
            </>
          ) : (
            <>
              <Play className="h-4 w-4" />
              Start Training
            </>
          )}
        </Button>
      </div>

      {/* Lista jobów */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-zinc-300">
          Historia Treningów ({jobs.length})
        </h3>
        <div className="space-y-2">
          {jobs.length === 0 ? (
            <div className="rounded-xl border border-white/10 bg-white/5 p-8 text-center">
              <p className="text-sm text-zinc-400">Brak jobów treningowych</p>
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
                        {job.status}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-zinc-400">
                      Started: {new Date(job.started_at).toLocaleString("pl-PL")}
                    </p>
                    {job.finished_at && (
                      <p className="text-xs text-zinc-400">
                        Finished: {new Date(job.finished_at).toLocaleString("pl-PL")}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <p className="text-xs text-zinc-400">Epochs: {job.parameters.num_epochs}</p>
                      <p className="text-xs text-zinc-400">LoRA: {job.parameters.lora_rank}</p>
                    </div>
                    <Button
                      onClick={() => setViewingLogs(job.job_id)}
                      variant="outline"
                      size="sm"
                      className="gap-2"
                    >
                      <Terminal className="h-4 w-4" />
                      Logs
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
