"use client";

import type { QueueStatus } from "@/lib/types";
import { CockpitQueueControl } from "@/components/cockpit/cockpit-queue-control";

type CockpitQueueProps = Readonly<{
  queue: QueueStatus | null;
  queueAction: string | null;
  queueActionMessage: string | null;
  onToggleQueue: () => void;
  onExecuteQueueMutation: (action: "purge" | "emergency") => void;
}>;

export function CockpitQueue({
  queue,
  queueAction,
  queueActionMessage,
  onToggleQueue,
  onExecuteQueueMutation,
}: CockpitQueueProps) {
  return (
    <CockpitQueueControl
      queue={queue}
      queueAction={queueAction}
      queueActionMessage={queueActionMessage}
      onToggleQueue={onToggleQueue}
      onExecuteQueueMutation={onExecuteQueueMutation}
    />
  );
}
