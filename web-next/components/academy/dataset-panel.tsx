"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Database, Play, Loader2, Upload, Trash2, Eye, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { useToast } from "@/components/ui/toast";
import {
  ConfirmDialog,
  ConfirmDialogActions,
  ConfirmDialogContent,
  ConfirmDialogDescription,
  ConfirmDialogTitle,
} from "@/components/ui/confirm-dialog";
import {
  curateDatasetV2,
  uploadDatasetFiles,
  listDatasetUploads,
  listDatasetConversionFiles,
  deleteDatasetUpload,
  previewDataset,
  resolveAcademyApiErrorMessage,
  type DatasetResponse,
  type DatasetConversionFileInfo,
  type UploadFileInfo,
  type DatasetPreviewResponse,
} from "@/lib/academy-api";
import { useLanguage, useTranslation } from "@/lib/i18n";

export function DatasetPanel() {
  const t = useTranslation();
  const { language } = useLanguage();
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DatasetResponse | null>(null);
  const [lessonsLimit, setLessonsLimit] = useState(200);
  const [gitLimit, setGitLimit] = useState(100);

  // Upload state
  const [uploading, setUploading] = useState(false);
  const [uploads, setUploads] = useState<UploadFileInfo[]>([]);
  const [convertedFiles, setConvertedFiles] = useState<DatasetConversionFileInfo[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const convertedSelectionInitializedRef = useRef(false);

  // Scope selection state
  const [includeLessons, setIncludeLessons] = useState(true);
  const [includeGit, setIncludeGit] = useState(true);
  const [includeTaskHistory, setIncludeTaskHistory] = useState(false);
  const [selectedUploadIds, setSelectedUploadIds] = useState<string[]>([]);
  const [selectedConvertedIds, setSelectedConvertedIds] = useState<string[]>([]);

  // Preview state
  const [preview, setPreview] = useState<DatasetPreviewResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{
    open: boolean;
    fileId: string | null;
  }>({ open: false, fileId: null });

  const loadUploads = useCallback(async () => {
    try {
      const data = await listDatasetUploads();
      setUploads(data);
    } catch (err) {
      console.error("Failed to load uploads:", err);
    }
  }, []);

  const loadConvertedFiles = useCallback(async () => {
    try {
      const data = await listDatasetConversionFiles();
      const ready = data.converted_files;
      setConvertedFiles(ready);
      setSelectedConvertedIds((prev) => {
        const valid = new Set(ready.map((file) => file.file_id));
        const kept = prev.filter((id) => valid.has(id));
        if (convertedSelectionInitializedRef.current) {
          return kept;
        }
        convertedSelectionInitializedRef.current = true;
        if (kept.length > 0) {
          return kept;
        }
        return ready
          .filter((file) => file.selected_for_training === true)
          .map((file) => file.file_id);
      });
    } catch (err) {
      console.error("Failed to load converted files:", err);
    }
  }, []);

  const loadSources = useCallback(async () => {
    await Promise.all([loadUploads(), loadConvertedFiles()]);
  }, [loadUploads, loadConvertedFiles]);

  // Load sources on mount
  useEffect(() => {
    loadSources().catch(() => undefined);
  }, [loadSources]);

  async function handleFileUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    try {
      setUploading(true);
      const result = await uploadDatasetFiles({ files });
      await loadSources();
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      pushToast(result.message, result.failed > 0 ? "warning" : "success");
      // Show result message with details about failures if any
      if (result.failed > 0) {
        result.errors.forEach((entry) => {
          pushToast(`${entry.name}: ${entry.error}`, "error");
        });
      }
    } catch (err) {
      console.error("Failed to upload files:", err);
      pushToast(err instanceof Error ? err.message : t("academy.dataset.uploadFailed"), "error");
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteUpload(fileId: string) {
    try {
      await deleteDatasetUpload(fileId);
      await loadSources();
      setSelectedUploadIds((prev) => prev.filter((id) => id !== fileId));
      pushToast(t("academy.dataset.fileDeleted"), "success");
    } catch (err) {
      console.error("Failed to delete upload:", err);
      pushToast(resolveAcademyApiErrorMessage(err), "error");
    }
  }

  function toggleUploadSelection(fileId: string) {
    setSelectedUploadIds((prev) =>
      prev.includes(fileId) ? prev.filter((id) => id !== fileId) : [...prev, fileId]
    );
  }

  function toggleConvertedSelection(fileId: string) {
    setSelectedConvertedIds((prev) =>
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
        conversion_file_ids: selectedConvertedIds,
        format: "alpaca",
      });
      setPreview(data);
    } catch (err) {
      console.error("Failed to preview dataset:", err);
      pushToast(resolveAcademyApiErrorMessage(err), "error");
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
        conversion_file_ids: selectedConvertedIds,
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
        message: resolveAcademyApiErrorMessage(err),
      });
    } finally {
      setLoading(false);
    }
  }

  function sourceLabel(source: string) {
    switch (source) {
      case "lessons":
        return t("academy.dataset.sources.lessons");
      case "git":
        return t("academy.dataset.sources.git");
      case "task_history":
        return t("academy.dataset.sources.taskHistory");
      case "uploads":
        return t("academy.dataset.sources.uploads");
      case "converted":
        return t("academy.dataset.sources.converted");
      default:
        return source;
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-[color:var(--text-heading)]">{t("academy.dataset.title")}</h2>
        <p className="text-sm text-hint">
          {t("academy.dataset.subtitle")}
        </p>
      </div>

      {/* User Uploads Section */}
      <div className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-6">
        <h3 className="text-base font-semibold text-[color:var(--text-heading)] mb-4">{t("academy.dataset.yourFiles")}</h3>

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
                  {t("academy.dataset.uploading")}
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4" />
                  {t("academy.dataset.uploadFiles")}
                </>
              )}
            </Button>
            <p className="mt-2 text-xs text-hint">
              {t("academy.dataset.supported")}
            </p>
          </div>

          {uploads.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-[color:var(--text-secondary)]">{t("academy.dataset.uploadedFiles")}</p>
              {uploads.map((upload) => (
                <div
                  key={upload.id}
                  className="flex items-center gap-3 rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-3"
                >
                  <Checkbox
                    checked={selectedUploadIds.includes(upload.id)}
                    onCheckedChange={() => toggleUploadSelection(upload.id)}
                  />
                  <div className="flex-1">
                    <p className="text-sm text-[color:var(--text-primary)]">{upload.name}</p>
                    <p className="text-xs text-hint">
                      {(upload.size_bytes / 1024).toFixed(1)} KB • ~{upload.records_estimate} {t("academy.dataset.records")} • {new Date(upload.created_at).toLocaleString(language)}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setDeleteConfirm({ open: true, fileId: upload.id })}
                    className="text-[color:var(--text-heading)] hover:text-red-400"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}

          {convertedFiles.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-[color:var(--text-secondary)]">
                {t("academy.dataset.convertedReadyFiles")}
              </p>
              {convertedFiles.map((file) => (
                <div
                  key={file.file_id}
                  className="flex items-center gap-3 rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-3"
                >
                  <Checkbox
                    checked={selectedConvertedIds.includes(file.file_id)}
                    onCheckedChange={() => toggleConvertedSelection(file.file_id)}
                  />
                  <div className="flex-1">
                    <p className="text-sm text-[color:var(--text-primary)]">{file.name}</p>
                    <p className="text-xs text-hint">
                      {(file.size_bytes / 1024).toFixed(1)} KB • {new Date(file.created_at).toLocaleString(language)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}

        </div>
      </div>

      {/* Training Scope Section */}
      <div className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-6">
        <h3 className="text-base font-semibold text-[color:var(--text-heading)] mb-4">{t("academy.dataset.trainingScope")}</h3>

        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Checkbox
              id="include-lessons"
              checked={includeLessons}
              onCheckedChange={(checked) => setIncludeLessons(checked === true)}
            />
            <Label htmlFor="include-lessons" className="text-[color:var(--text-secondary)] cursor-pointer">
              {t("academy.dataset.lessonsStore")}
            </Label>
          </div>

          {includeLessons && (
            <div className="ml-6">
              <Label htmlFor="lessons-limit" className="text-[color:var(--text-secondary)] text-sm">
                {t("academy.dataset.lessonsLimit")}
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
              onCheckedChange={(checked) => setIncludeGit(checked === true)}
            />
            <Label htmlFor="include-git" className="text-[color:var(--text-secondary)] cursor-pointer">
              {t("academy.dataset.gitHistory")}
            </Label>
          </div>

          {includeGit && (
            <div className="ml-6">
              <Label htmlFor="git-limit" className="text-[color:var(--text-secondary)] text-sm">
                {t("academy.dataset.commitsLimit")}
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
              onCheckedChange={(checked) => setIncludeTaskHistory(checked === true)}
            />
            <Label htmlFor="include-task-history" className="text-[color:var(--text-secondary)] cursor-pointer">
              {t("academy.dataset.taskHistoryExperimental")}
            </Label>
          </div>

          {selectedUploadIds.length > 0 && (
            <div className="mt-2 rounded-lg border border-[color:var(--stat-card-blue-border)] bg-[color:var(--stat-card-blue-bg)] p-3">
              <p className="text-sm text-[color:var(--stat-card-blue-text)]">
                ✓ {t("academy.dataset.selectedUploads", { count: selectedUploadIds.length })}
              </p>
            </div>
          )}

          {selectedConvertedIds.length > 0 && (
            <div className="mt-2 rounded-lg border border-[color:var(--stat-card-emerald-border)] bg-[color:var(--stat-card-emerald-bg)] p-3">
              <p className="text-sm text-[color:var(--stat-card-emerald-text)]">
                ✓ {t("academy.dataset.selectedConverted", { count: selectedConvertedIds.length })}
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
                {t("academy.dataset.generating")}
              </>
            ) : (
              <>
                <Eye className="h-4 w-4" />
                {t("academy.dataset.preview")}
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
                {t("academy.dataset.curating")}
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                {t("academy.dataset.curateDataset")}
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Preview Results */}
      {preview && (
        <div className="rounded-xl border border-[color:var(--stat-card-blue-border)] bg-[color:var(--stat-card-blue-bg)] p-6">
          <div className="flex items-start gap-3">
            <Eye className="h-6 w-6 text-[color:var(--stat-card-blue-text)]" />
            <div className="flex-1">
              <p className="font-medium text-[color:var(--stat-card-blue-text)]">{t("academy.dataset.previewTitle")}</p>

              <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <p className="text-xs text-hint">{t("academy.dataset.totalCount")}</p>
                  <p className="mt-1 text-lg font-semibold text-[color:var(--text-primary)]">
                    {preview.total_examples}
                  </p>
                </div>
                {Object.entries(preview.by_source).map(([source, count]) => (
                  <div key={source}>
                    <p className="text-xs text-hint capitalize">{sourceLabel(source)}</p>
                    <p className="mt-1 text-lg font-semibold text-[color:var(--text-primary)]">{count}</p>
                  </div>
                ))}
                <div>
                  <p className="text-xs text-hint">{t("academy.dataset.rejected")}</p>
                  <p className="mt-1 text-lg font-semibold text-[color:var(--text-primary)]">
                    {preview.removed_low_quality}
                  </p>
                </div>
              </div>

              {preview.warnings.length > 0 && (
                <div className="mt-4 space-y-2">
                  {preview.warnings.map((warning) => (
                    <div key={warning} className="flex items-start gap-2 text-sm text-[color:var(--stat-card-yellow-text)]">
                      <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                      <p>{warning}</p>
                    </div>
                  ))}
                </div>
              )}

              {preview.samples.length > 0 && (
                <div className="mt-4">
                  <p className="text-sm font-medium text-[color:var(--text-primary)] mb-2">{t("academy.dataset.sampleRecords")}</p>
                  <div className="space-y-2">
                    {preview.samples.slice(0, 3).map((sample) => (
                      <div
                        key={`${sample.instruction}:${sample.input}:${sample.output}`}
                        className="rounded-lg bg-[color:var(--surface-muted)] p-3 text-xs"
                      >
                        <p className="text-[color:var(--stat-card-blue-text)] font-medium">📝 {sample.instruction}</p>
                        {sample.input && <p className="text-hint mt-1">➡️ {sample.input}</p>}
                        <p className="text-[color:var(--text-secondary)] mt-1">✓ {sample.output}</p>
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
        <div className={`rounded-xl border p-6 ${result.success
            ? "border-[color:var(--stat-card-emerald-border)] bg-[color:var(--stat-card-emerald-bg)]"
            : "border-[color:var(--stat-card-red-border)] bg-[color:var(--stat-card-red-bg)]"
          }`}>
          <div className="flex items-start gap-3">
            <Database className={`h-6 w-6 ${result.success ? "text-[color:var(--stat-card-emerald-text)]" : "text-[color:var(--stat-card-red-text)]"
              }`} />
            <div className="flex-1">
              <p className={`font-medium ${result.success ? "text-[color:var(--stat-card-emerald-text)]" : "text-[color:var(--stat-card-red-text)]"
                }`}>
                {result.message}
              </p>

              {result.success && result.statistics && (
                <div className="mt-4">
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 mb-4">
                    <div>
                      <p className="text-xs text-hint">{t("academy.dataset.totalCount")}</p>
                      <p className="mt-1 text-lg font-semibold text-[color:var(--text-primary)]">
                        {result.statistics.total_examples}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-hint">{t("academy.dataset.removed")}</p>
                      <p className="mt-1 text-lg font-semibold text-[color:var(--text-primary)]">
                        {result.statistics.removed_low_quality}
                      </p>
                    </div>
                  </div>

                  {result.statistics.by_source && (
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                      {Object.entries(result.statistics.by_source).map(([source, count]) => (
                        <div key={source} className="rounded-lg bg-[color:var(--ui-surface)] p-2">
                          <p className="text-xs text-hint capitalize">{sourceLabel(source)}</p>
                          <p className="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">{count}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {result.dataset_path && (
                <p className="mt-3 text-xs font-mono text-hint">
                  📁 {result.dataset_path}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Information */}
      <div className="rounded-xl border border-[color:var(--stat-card-blue-border)] bg-[color:var(--stat-card-blue-bg)] p-4">
        <p className="text-sm text-[color:var(--stat-card-blue-text)] font-medium mb-2">
          ℹ️ {t("academy.dataset.infoTitle")}
        </p>
        <p className="text-xs text-hint">
          {t("academy.dataset.infoDescription")}
        </p>
      </div>

      <ConfirmDialog
        open={deleteConfirm.open}
        onOpenChange={(open) => setDeleteConfirm((prev) => ({ ...prev, open }))}
      >
        <ConfirmDialogContent>
          <ConfirmDialogTitle>{t("academy.dataset.deleteDialogTitle")}</ConfirmDialogTitle>
          <ConfirmDialogDescription>
            {t("academy.dataset.deleteDialogDescription")}
          </ConfirmDialogDescription>
          <ConfirmDialogActions
            onCancel={() => setDeleteConfirm({ open: false, fileId: null })}
            onConfirm={async () => {
              const { fileId } = deleteConfirm;
              setDeleteConfirm({ open: false, fileId: null });
              if (!fileId) return;
              await handleDeleteUpload(fileId);
            }}
            confirmLabel={t("academy.dataset.delete")}
            cancelLabel={t("academy.dataset.cancel")}
            confirmVariant="danger"
          />
        </ConfirmDialogContent>
      </ConfirmDialog>
    </div>
  );
}
