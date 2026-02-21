"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FileText, Loader2, Upload, WandSparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useToast } from "@/components/ui/toast";
import {
  convertDatasetFile,
  listDatasetConversionFiles,
  previewDatasetFile,
  setDatasetConversionTrainingSelection,
  uploadDatasetConversionFiles,
  type DatasetConversionFileInfo,
} from "@/lib/academy-api";
import { useTranslation } from "@/lib/i18n";

const TARGET_FORMATS = ["md", "txt", "json", "jsonl", "csv"] as const;
type TargetFormat = (typeof TARGET_FORMATS)[number];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DatasetConversionPanel() {
  const t = useTranslation();
  const { pushToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [convertingId, setConvertingId] = useState<string | null>(null);
  const [selectionUpdatingId, setSelectionUpdatingId] = useState<string | null>(null);
  const [targetBySource, setTargetBySource] = useState<Record<string, TargetFormat>>({});
  const [sourceFiles, setSourceFiles] = useState<DatasetConversionFileInfo[]>([]);
  const [convertedFiles, setConvertedFiles] = useState<DatasetConversionFileInfo[]>([]);
  const [workspaceDir, setWorkspaceDir] = useState("");
  const [previewText, setPreviewText] = useState<string>("");
  const [previewTitle, setPreviewTitle] = useState<string>("");

  const allPreviewable = useMemo(() => {
    return [...sourceFiles, ...convertedFiles].filter((item) => [".txt", ".md"].includes(item.extension));
  }, [sourceFiles, convertedFiles]);

  const loadFiles = useCallback(async () => {
    try {
      setLoading(true);
      const response = await listDatasetConversionFiles();
      setSourceFiles(response.source_files);
      setConvertedFiles(response.converted_files);
      setWorkspaceDir(response.workspace_dir);
      setTargetBySource((previous) => {
        const next: Record<string, TargetFormat> = { ...previous };
        response.source_files.forEach((item) => {
          if (!next[item.file_id]) {
            next[item.file_id] = "md";
          }
        });
        return next;
      });
    } catch (error) {
      pushToast(
        error instanceof Error ? error.message : t("academy.conversion.loadFailed"),
        "error"
      );
    } finally {
      setLoading(false);
    }
  }, [pushToast, t]);

  useEffect(() => {
    loadFiles().catch(() => undefined);
  }, [loadFiles]);

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    try {
      setUploading(true);
      const result = await uploadDatasetConversionFiles({ files });
      pushToast(result.message, result.failed > 0 ? "warning" : "success");
      await loadFiles();
    } catch (error) {
      pushToast(error instanceof Error ? error.message : t("academy.conversion.uploadFailed"), "error");
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      setUploading(false);
    }
  }

  async function handleConvert(file: DatasetConversionFileInfo) {
    const targetFormat = targetBySource[file.file_id] ?? "md";
    try {
      setConvertingId(file.file_id);
      const result = await convertDatasetFile({ fileId: file.file_id, targetFormat });
      pushToast(result.message, "success");
      await loadFiles();
    } catch (error) {
      pushToast(error instanceof Error ? error.message : t("academy.conversion.convertFailed"), "error");
    } finally {
      setConvertingId(null);
    }
  }

  async function handlePreview(file: DatasetConversionFileInfo) {
    try {
      const preview = await previewDatasetFile(file.file_id);
      setPreviewTitle(preview.name);
      setPreviewText(preview.preview);
    } catch (error) {
      pushToast(error instanceof Error ? error.message : t("academy.conversion.previewFailed"), "error");
    }
  }

  async function handleTrainingSelection(file: DatasetConversionFileInfo, selected: boolean) {
    try {
      setSelectionUpdatingId(file.file_id);
      await setDatasetConversionTrainingSelection({
        fileId: file.file_id,
        selectedForTraining: selected,
      });
      await loadFiles();
    } catch (error) {
      pushToast(
        error instanceof Error ? error.message : t("academy.conversion.trainingSelectionFailed"),
        "error"
      );
    } finally {
      setSelectionUpdatingId(null);
    }
  }

  function onTrainingSelectionChange(file: DatasetConversionFileInfo, checked: boolean) {
    handleTrainingSelection(file, checked).catch(() => undefined);
  }

  function onPreviewClick(file: DatasetConversionFileInfo) {
    handlePreview(file).catch(() => undefined);
  }

  function onConvertClick(file: DatasetConversionFileInfo) {
    handleConvert(file).catch(() => undefined);
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">{t("academy.conversion.title")}</h2>
        <p className="text-sm text-zinc-400">{t("academy.conversion.subtitle")}</p>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.doc,.docx,.jsonl,.json,.md,.txt,.csv"
            onChange={handleUpload}
            className="hidden"
          />
          <Button onClick={() => fileInputRef.current?.click()} disabled={uploading} variant="outline" className="gap-2">
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            {uploading ? t("academy.conversion.uploading") : t("academy.conversion.uploadFiles")}
          </Button>
          <p className="text-xs text-zinc-400">{t("academy.conversion.supported")}</p>
        </div>
        {workspaceDir ? (
          <p className="mt-3 text-xs text-zinc-500">
            {t("academy.conversion.workspace")}: <code>{workspaceDir}</code>
          </p>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <h3 className="mb-3 text-sm font-semibold text-white">{t("academy.conversion.convertedFiles")}</h3>
          <div className="space-y-2">
            {loading ? (
              <p className="text-sm text-zinc-400">{t("academy.common.loadingAcademy")}</p>
            ) : convertedFiles.length === 0 ? (
              <p className="text-sm text-zinc-400">{t("academy.conversion.emptyConverted")}</p>
            ) : (
              convertedFiles.map((file) => (
                <div key={file.file_id} className="rounded-lg border border-white/10 bg-black/20 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm text-white">{file.name}</p>
                    <span className="text-xs text-zinc-500">{formatFileSize(file.size_bytes)}</span>
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <Checkbox
                      checked={file.selected_for_training === true}
                      disabled={selectionUpdatingId === file.file_id}
                      onCheckedChange={(checked) => onTrainingSelectionChange(file, checked === true)}
                    />
                    <span className="text-xs text-zinc-300">
                      {t("academy.conversion.useForTraining")}
                    </span>
                    {selectionUpdatingId === file.file_id ? (
                      <Loader2 className="h-3 w-3 animate-spin text-zinc-400" />
                    ) : null}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {[".txt", ".md"].includes(file.extension) ? (
                      <Button size="sm" variant="ghost" onClick={() => onPreviewClick(file)}>
                        {t("academy.conversion.preview")}
                      </Button>
                    ) : null}
                    <a
                      href={`/api/v1/academy/dataset/conversion/files/${file.file_id}/download`}
                      className="inline-flex items-center rounded-md border border-white/15 px-2 py-1 text-xs text-zinc-200 hover:bg-white/5"
                    >
                      {t("academy.conversion.download")}
                    </a>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <h3 className="mb-3 text-sm font-semibold text-white">{t("academy.conversion.sourceFiles")}</h3>
          <div className="space-y-2">
            {loading ? (
              <p className="text-sm text-zinc-400">{t("academy.common.loadingAcademy")}</p>
            ) : sourceFiles.length === 0 ? (
              <p className="text-sm text-zinc-400">{t("academy.conversion.emptySource")}</p>
            ) : (
              sourceFiles.map((file) => (
                <div key={file.file_id} className="rounded-lg border border-white/10 bg-black/20 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm text-white">{file.name}</p>
                    <span className="text-xs text-zinc-500">{formatFileSize(file.size_bytes)}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <select
                      value={targetBySource[file.file_id] ?? "md"}
                      onChange={(event) =>
                        setTargetBySource((prev) => ({
                          ...prev,
                          [file.file_id]: event.target.value as TargetFormat,
                        }))
                      }
                      className="rounded-md border border-white/15 bg-[#03162a] px-2 py-1 text-xs text-zinc-200"
                    >
                      {TARGET_FORMATS.map((format) => (
                        <option key={format} value={format}>
                          .{format}
                        </option>
                      ))}
                    </select>
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1"
                      disabled={convertingId === file.file_id}
                      onClick={() => onConvertClick(file)}
                    >
                      {convertingId === file.file_id ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <WandSparkles className="h-3 w-3" />
                      )}
                      {t("academy.conversion.convert")}
                    </Button>
                    {[".txt", ".md"].includes(file.extension) ? (
                      <Button size="sm" variant="ghost" onClick={() => onPreviewClick(file)}>
                        {t("academy.conversion.preview")}
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-white">
          <FileText className="h-4 w-4" />
          {previewTitle || t("academy.conversion.previewPanel")}
        </div>
        <textarea
          value={previewText}
          readOnly
          className="min-h-[280px] w-full rounded-lg border border-white/10 bg-[#020e1e] p-3 text-xs text-zinc-200"
          placeholder={
            allPreviewable.length > 0
              ? t("academy.conversion.previewHint")
              : t("academy.conversion.noPreviewableFiles")
          }
        />
      </div>
    </div>
  );
}
