"use client";

import { useState } from "react";
import { Database, Play, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { curateDataset, type AcademyStatus, type DatasetResponse } from "@/lib/academy-api";

interface DatasetPanelProps {
  status: AcademyStatus;
}

export function DatasetPanel({ }: DatasetPanelProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DatasetResponse | null>(null);
  const [lessonsLimit, setLessonsLimit] = useState(200);
  const [gitLimit, setGitLimit] = useState(100);

  async function handleCurate() {
    try {
      setLoading(true);
      setResult(null);
      const data = await curateDataset({
        lessons_limit: lessonsLimit,
        git_commits_limit: gitLimit,
        format: "alpaca",
      });
      setResult(data);
    } catch (err) {
      console.error("Failed to curate dataset:", err);
      setResult({
        success: false,
        statistics: {
          total_examples: 0,
          lessons_collected: 0,
          git_commits_collected: 0,
          removed_low_quality: 0,
          avg_input_length: 0,
          avg_output_length: 0,
        },
        message: err instanceof Error ? err.message : "Failed to curate dataset",
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">Kuracja Datasetu</h2>
        <p className="text-sm text-zinc-400">
          Przygotowanie danych treningowych z LessonsStore i Git History
        </p>
      </div>

      {/* Formularz */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="lessons-limit" className="text-zinc-300">
              Limit lekcji
            </Label>
            <Input
              id="lessons-limit"
              type="number"
              value={lessonsLimit}
              onChange={(e) => setLessonsLimit(parseInt(e.target.value) || 0)}
              min={10}
              max={1000}
              className="mt-2"
            />
            <p className="mt-1 text-xs text-zinc-400">Maksimum lekcji z LessonsStore (10-1000)</p>
          </div>
          <div>
            <Label htmlFor="git-limit" className="text-zinc-300">
              Limit commitów Git
            </Label>
            <Input
              id="git-limit"
              type="number"
              value={gitLimit}
              onChange={(e) => setGitLimit(parseInt(e.target.value) || 0)}
              min={0}
              max={500}
              className="mt-2"
            />
            <p className="mt-1 text-xs text-zinc-400">Maksimum commitów z Git History (0-500)</p>
          </div>
        </div>

        <Button
          onClick={handleCurate}
          disabled={loading}
          className="mt-4 gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Kuracja w trakcie...
            </>
          ) : (
            <>
              <Play className="h-4 w-4" />
              Kuruj Dataset
            </>
          )}
        </Button>
      </div>

      {/* Wynik */}
      {result && (
        <div className={`rounded-xl border p-6 ${
          result.success
            ? "border-emerald-500/20 bg-emerald-500/5"
            : "border-red-500/20 bg-red-500/5"
        }`}>
          <div className="flex items-start gap-3">
            <Database className={`h-6 w-6 ${
              result.success ? "text-emerald-400" : "text-red-400"
            }`} />
            <div className="flex-1">
              <p className={`font-medium ${
                result.success ? "text-emerald-300" : "text-red-300"
              }`}>
                {result.message}
              </p>
              
              {result.success && result.statistics && (
                <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <div>
                    <p className="text-xs text-zinc-400">Łączna liczba</p>
                    <p className="mt-1 text-lg font-semibold text-white">
                      {result.statistics.total_examples}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-zinc-400">Z Lessons</p>
                    <p className="mt-1 text-lg font-semibold text-white">
                      {result.statistics.lessons_collected}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-zinc-400">Z Git</p>
                    <p className="mt-1 text-lg font-semibold text-white">
                      {result.statistics.git_commits_collected}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-zinc-400">Usunięto</p>
                    <p className="mt-1 text-lg font-semibold text-white">
                      {result.statistics.removed_low_quality}
                    </p>
                  </div>
                </div>
              )}

              {result.dataset_path && (
                <p className="mt-2 text-xs font-mono text-zinc-400">
                  📁 {result.dataset_path}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Informacje */}
      <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-4">
        <p className="text-sm text-blue-300">
          ℹ️ Dataset będzie zawierał przykłady z LessonsStore (successful experiences) i Git History
          (commits z diff → message).
        </p>
        <p className="mt-2 text-xs text-zinc-400">
          Format: Alpaca JSONL (instruction-input-output). Minimalna jakość przykładów jest filtrowana automatycznie.
        </p>
      </div>
    </div>
  );
}
