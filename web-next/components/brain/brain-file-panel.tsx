import { Panel } from "@/components/ui/panel";
import { FileAnalysisForm, FileAnalysisPanel } from "@/components/brain/file-analytics";

type BrainFilePanelProps = Readonly<{
  title: string;
  description: string;
  filePath: string;
  loading: boolean;
  message: string | null;
  fileInfo: Record<string, unknown> | null;
  impactInfo: Record<string, unknown> | null;
  onPathChange: (value: string) => void;
  onFileInfo: () => void;
  onImpact: () => void;
}>;

export function BrainFilePanel({
  title,
  description,
  filePath,
  loading,
  message,
  fileInfo,
  impactInfo,
  onPathChange,
  onFileInfo,
  onImpact,
}: BrainFilePanelProps) {
  return (
    <Panel title={title} description={description}>
      <div data-testid="brain-file-panel">
        <FileAnalysisForm
          filePath={filePath}
          onPathChange={onPathChange}
          loading={loading}
          onFileInfo={onFileInfo}
          onImpact={onImpact}
          message={message}
        />
        <div className="grid gap-4 md:grid-cols-2">
          <FileAnalysisPanel label="File info" payload={fileInfo} />
          <FileAnalysisPanel label="Impact" payload={impactInfo} />
        </div>
      </div>
    </Panel>
  );
}
