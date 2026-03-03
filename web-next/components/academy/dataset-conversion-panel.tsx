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
const PREVIEWABLE_EXTENSIONS = new Set([".txt", ".md"]);

function isPreviewableExtension(extension: string): boolean {
  return PREVIEWABLE_EXTENSIONS.has(extension);
}

function mergeTargetFormat(
  previous: Record<string, TargetFormat>,
  fileId: string,
  targetFormat: TargetFormat
): Record<string, TargetFormat> {
  return {
    ...previous,
    [fileId]: targetFormat,
  };
}

function toTargetFormat(value: string): TargetFormat {
  return TARGET_FORMATS.includes(value as TargetFormat) ? (value as TargetFormat) : "md";
}

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

  const handleTargetFormatChange = useCallback((fileId: string, rawValue: string) => {
    const targetFormat = toTargetFormat(rawValue);
    setTargetBySource((previous) => mergeTargetFormat(previous, fileId, targetFormat));
  }, []);

  const handleTargetFormatSelectChange = useCallback(
    (event: React.ChangeEvent<HTMLSelectElement>) => {
      const fileId = event.currentTarget.dataset.fileId;
      if (!fileId) return;
      handleTargetFormatChange(fileId, event.currentTarget.value);
    },
    [handleTargetFormatChange]
  );

  const renderConvertedListContent = () => {
    if (loading) {
      return <p className="text-sm text-hint">{t("academy.common.loadingAcademy")}</p>;
    }
    if (convertedFiles.length === 0) {
      return <p className="text-sm text-hint">{t("academy.conversion.emptyConverted")}</p>;
    }
    return convertedFiles.map((file) => (
      <div key={file.file_id} className="rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-3 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-sm font-medium text-[color:var(--text-primary)]">{file.name}</p>
          <span className="text-xs text-hint">{formatFileSize(file.size_bytes)}</span>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <Checkbox
            checked={file.selected_for_training === true}
            disabled={selectionUpdatingId === file.file_id}
            onCheckedChange={(checked) => onTrainingSelectionChange(file, checked === true)}
          />
          <span className="text-xs text-[color:var(--text-secondary)]">{t("academy.conversion.useForTraining")}</span>
          {selectionUpdatingId === file.file_id ? (
            <Loader2 className="h-3 w-3 animate-spin text-hint" />
          ) : null}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {isPreviewableExtension(file.extension) ? (
            <Button size="sm" variant="ghost" onClick={() => onPreviewClick(file)}>
              {t("academy.conversion.preview")}
            </Button>
          ) : null}
          <a
            href={`/api/v1/academy/dataset/conversion/files/${file.file_id}/download`}
            className="inline-flex items-center rounded-md border border-[color:var(--ui-border)] px-2 py-1 text-xs text-[color:var(--text-secondary)] hover:bg-[color:var(--ui-surface-hover)]"
          >
            {t("academy.conversion.download")}
          </a>
        </div>
      </div>
    ));
  };

  const renderSourceListContent = () => {
    if (loading) {
      return <p className="text-sm text-hint">{t("academy.common.loadingAcademy")}</p>;
    }
    if (sourceFiles.length === 0) {
      return <p className="text-sm text-hint">{t("academy.conversion.emptySource")}</p>;
    }
    return sourceFiles.map((file) => (
      <div key={file.file_id} className="rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-3 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-sm font-medium text-[color:var(--text-primary)]">{file.name}</p>
          <span className="text-xs text-hint">{formatFileSize(file.size_bytes)}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select
            data-file-id={file.file_id}
            value={targetBySource[file.file_id] ?? "md"}
            onChange={handleTargetFormatSelectChange}
            className="rounded-md border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] px-2 py-1 text-xs text-[color:var(--text-primary)]"
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
          {isPreviewableExtension(file.extension) ? (
            <Button size="sm" variant="ghost" onClick={() => onPreviewClick(file)}>
              {t("academy.conversion.preview")}
            </Button>
          ) : null}
        </div>
      </div>
    ));
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-[color:var(--text-heading)]">{t("academy.conversion.title")}</h2>
        <p className="text-sm text-hint">{t("academy.conversion.subtitle")}</p>
      </div>

      <div className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4">
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
          <p className="text-xs text-hint">{t("academy.conversion.supported")}</p>
        </div>
        {workspaceDir ? (
          <p className="mt-3 text-xs text-hint/60">
            {t("academy.conversion.workspace")}: <code>{workspaceDir}</code>
          </p>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4">
          <h3 className="mb-3 text-sm font-semibold text-[color:var(--text-heading)]">{t("academy.conversion.convertedFiles")}</h3>
          <div className="space-y-2">
            {renderConvertedListContent()}
          </div>
        </div>

        <div className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4">
          <h3 className="mb-3 text-sm font-semibold text-[color:var(--text-heading)]">{t("academy.conversion.sourceFiles")}</h3>
          <div className="space-y-2">
            {renderSourceListContent()}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4 shadow-sm">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-[color:var(--text-primary)]">
          <FileText className="h-4 w-4" />
          {previewTitle || t("academy.conversion.previewPanel")}
        </div>
        <textarea
          value={previewText}
          readOnly
          className="min-h-[280px] w-full rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--terminal)] p-3 text-xs text-[color:var(--text-primary)]"
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
