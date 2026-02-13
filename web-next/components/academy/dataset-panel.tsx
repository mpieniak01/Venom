"use client";

import { useState, useEffect, useRef } from "react";
import { Database, Play, Loader2, Upload, Trash2, Eye, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  curateDatasetV2,
  uploadDatasetFiles,
  listDatasetUploads,
  deleteDatasetUpload,
  previewDataset,
  type DatasetResponse,
  type UploadFileInfo,
  type DatasetPreviewResponse,
} from "@/lib/academy-api";

export function DatasetPanel() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DatasetResponse | null>(null);
  const [lessonsLimit, setLessonsLimit] = useState(200);
  const [gitLimit, setGitLimit] = useState(100);
  
  // Upload state
  const [uploading, setUploading] = useState(false);
  const [uploads, setUploads] = useState<UploadFileInfo[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // Scope selection state
  const [includeLessons, setIncludeLessons] = useState(true);
  const [includeGit, setIncludeGit] = useState(true);
  const [includeTaskHistory, setIncludeTaskHistory] = useState(false);
  const [selectedUploadIds, setSelectedUploadIds] = useState<string[]>([]);
  
  // Preview state
  const [preview, setPreview] = useState<DatasetPreviewResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);

  // Load uploads on mount
  useEffect(() => {
    loadUploads();
  }, []);

  async function loadUploads() {
    try {
      const data = await listDatasetUploads();
      setUploads(data);
    } catch (err) {
      console.error("Failed to load uploads:", err);
    }
  }

  async function handleFileUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    try {
      setUploading(true);
      await uploadDatasetFiles({ files });
      await loadUploads();
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (err) {
      console.error("Failed to upload files:", err);
      alert(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteUpload(fileId: string) {
    if (!confirm("Are you sure you want to delete this file?")) return;

    try {
      await deleteDatasetUpload(fileId);
      await loadUploads();
      setSelectedUploadIds((prev) => prev.filter((id) => id !== fileId));
    } catch (err) {
      console.error("Failed to delete upload:", err);
      alert("Failed to delete file");
    }
  }

  function toggleUploadSelection(fileId: string) {
    setSelectedUploadIds((prev) =>
      prev.includes(fileId) ? prev.filter((id) => id !== fileId) : [...prev, fileId]
    );
  }

  async function handlePreview() {
    try {
      setPreviewing(true);
      setPreview(null);
      const data = await previewDataset({
        lessons_limit: lessonsLimit,
        git_commits_limit: gitLimit,
        include_task_history: includeTaskHistory,
        include_lessons: includeLessons,
        include_git: includeGit,
        upload_ids: selectedUploadIds,
        format: "alpaca",
      });
      setPreview(data);
    } catch (err) {
      console.error("Failed to preview dataset:", err);
      alert("Failed to generate preview");
    } finally {
      setPreviewing(false);
    }
  }

  async function handleCurate() {
    try {
      setLoading(true);
      setResult(null);
      const data = await curateDatasetV2({
        lessons_limit: lessonsLimit,
        git_commits_limit: gitLimit,
        include_task_history: includeTaskHistory,
        include_lessons: includeLessons,
        include_git: includeGit,
        upload_ids: selectedUploadIds,
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
        <h2 className="text-lg font-semibold text-white">Dataset Curation (v2)</h2>
        <p className="text-sm text-zinc-400">
          Prepare training data: select sources and upload your own files
        </p>
      </div>

      {/* User Uploads Section */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-6">
        <h3 className="text-base font-semibold text-white mb-4">Your Files</h3>
        
        <div className="space-y-4">
          <div>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".jsonl,.json,.md,.txt,.csv"
              onChange={handleFileUpload}
              className="hidden"
              id="file-upload"
            />
            <Button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              variant="outline"
              className="gap-2"
            >
              {uploading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Uploading...
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4" />
                  Upload Files
                </>
              )}
            </Button>
            <p className="mt-2 text-xs text-zinc-400">
              Supported: .jsonl, .json, .md, .txt, .csv
            </p>
          </div>

          {uploads.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-zinc-300">Uploaded files:</p>
              {uploads.map((upload) => (
                <div
                  key={upload.id}
                  className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/5 p-3"
                >
                  <Checkbox
                    checked={selectedUploadIds.includes(upload.id)}
                    onCheckedChange={() => toggleUploadSelection(upload.id)}
                  />
                  <div className="flex-1">
                    <p className="text-sm text-white">{upload.name}</p>
                    <p className="text-xs text-zinc-400">
                      {(upload.size_bytes / 1024).toFixed(1)} KB • ~{upload.records_estimate} records • {new Date(upload.created_at).toLocaleString()}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleDeleteUpload(upload.id)}
                    className="text-red-400 hover:text-red-300"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Training Scope Section */}
      <div className="rounded-xl border border-white/10 bg-white/5 p-6">
        <h3 className="text-base font-semibold text-white mb-4">Training Scope</h3>
        
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Checkbox
              id="include-lessons"
              checked={includeLessons}
              onCheckedChange={(checked) => setIncludeLessons(checked as boolean)}
            />
            <Label htmlFor="include-lessons" className="text-zinc-300 cursor-pointer">
              Lessons Store
            </Label>
          </div>

          {includeLessons && (
            <div className="ml-6">
              <Label htmlFor="lessons-limit" className="text-zinc-300 text-sm">
                Lessons limit
              </Label>
              <Input
                id="lessons-limit"
                type="number"
                value={lessonsLimit}
                onChange={(e) => setLessonsLimit(Number.parseInt(e.target.value, 10) || 0)}
                min={10}
                max={1000}
                className="mt-2 w-32"
              />
            </div>
          )}

          <div className="flex items-center gap-2">
            <Checkbox
              id="include-git"
              checked={includeGit}
              onCheckedChange={(checked) => setIncludeGit(checked as boolean)}
            />
            <Label htmlFor="include-git" className="text-zinc-300 cursor-pointer">
              Git History
            </Label>
          </div>

          {includeGit && (
            <div className="ml-6">
              <Label htmlFor="git-limit" className="text-zinc-300 text-sm">
                Commits limit
              </Label>
              <Input
                id="git-limit"
                type="number"
                value={gitLimit}
                onChange={(e) => setGitLimit(Number.parseInt(e.target.value, 10) || 0)}
                min={0}
                max={500}
                className="mt-2 w-32"
              />
            </div>
          )}

          <div className="flex items-center gap-2">
            <Checkbox
              id="include-task-history"
              checked={includeTaskHistory}
              onCheckedChange={(checked) => setIncludeTaskHistory(checked as boolean)}
            />
            <Label htmlFor="include-task-history" className="text-zinc-300 cursor-pointer">
              Task History (experimental)
            </Label>
          </div>

          {selectedUploadIds.length > 0 && (
            <div className="mt-2 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
              <p className="text-sm text-blue-300">
                ✓ {selectedUploadIds.length} uploaded file(s) will be included
              </p>
            </div>
          )}
        </div>

        <div className="mt-6 flex gap-3">
          <Button
            onClick={handlePreview}
            disabled={previewing}
            variant="outline"
            className="gap-2"
          >
            {previewing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generowanie...
              </>
            ) : (
              <>
                <Eye className="h-4 w-4" />
                Preview
              </>
            )}
          </Button>

          <Button
            onClick={handleCurate}
            disabled={loading}
            className="gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Curating...
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                Curate Dataset
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Preview Results */}
      {preview && (
        <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-6">
          <div className="flex items-start gap-3">
            <Eye className="h-6 w-6 text-blue-400" />
            <div className="flex-1">
              <p className="font-medium text-blue-300">Dataset Preview</p>

              <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <p className="text-xs text-zinc-400">Total Count</p>
                  <p className="mt-1 text-lg font-semibold text-white">
                    {preview.total_examples}
                  </p>
                </div>
                {Object.entries(preview.by_source).map(([source, count]) => (
                  <div key={source}>
                    <p className="text-xs text-zinc-400 capitalize">{source}</p>
                    <p className="mt-1 text-lg font-semibold text-white">{count}</p>
                  </div>
                ))}
                <div>
                  <p className="text-xs text-zinc-400">Rejected</p>
                  <p className="mt-1 text-lg font-semibold text-white">
                    {preview.removed_low_quality}
                  </p>
                </div>
              </div>

              {preview.warnings.length > 0 && (
                <div className="mt-4 space-y-2">
                  {preview.warnings.map((warning, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-sm text-yellow-400">
                      <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                      <p>{warning}</p>
                    </div>
                  ))}
                </div>
              )}

              {preview.samples.length > 0 && (
                <div className="mt-4">
                  <p className="text-sm font-medium text-zinc-300 mb-2">Sample records:</p>
                  <div className="space-y-2">
                    {preview.samples.slice(0, 3).map((sample, idx) => (
                      <div key={idx} className="rounded-lg bg-black/20 p-3 text-xs">
                        <p className="text-blue-300 font-medium">📝 {sample.instruction}</p>
                        {sample.input && <p className="text-zinc-400 mt-1">➡️ {sample.input}</p>}
                        <p className="text-zinc-300 mt-1">✓ {sample.output}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Curate Results */}
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
                <div className="mt-4">
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 mb-4">
                    <div>
                      <p className="text-xs text-zinc-400">Total Count</p>
                      <p className="mt-1 text-lg font-semibold text-white">
                        {result.statistics.total_examples}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-zinc-400">Removed</p>
                      <p className="mt-1 text-lg font-semibold text-white">
                        {result.statistics.removed_low_quality}
                      </p>
                    </div>
                  </div>

                  {result.statistics.by_source && (
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                      {Object.entries(result.statistics.by_source).map(([source, count]) => (
                        <div key={source} className="rounded-lg bg-white/5 p-2">
                          <p className="text-xs text-zinc-400 capitalize">{source}</p>
                          <p className="mt-1 text-sm font-semibold text-white">{count}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {result.dataset_path && (
                <p className="mt-3 text-xs font-mono text-zinc-400">
                  📁 {result.dataset_path}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Information */}
      <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-4">
        <p className="text-sm text-blue-300 font-medium mb-2">
          ℹ️ Academy v2: Training LoRA adapter, not full model
        </p>
        <p className="text-xs text-zinc-400">
          Dataset can include examples from LessonsStore, Git History, Task History, and your uploads.
          Training uses LoRA/QLoRA adapter on base model, not training from scratch.
          Format: Alpaca JSONL (instruction-input-output). Low quality examples are filtered automatically.
        </p>
      </div>
    </div>
  );
}
