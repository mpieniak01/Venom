import { canonicalRuntimeId } from "@/lib/runtime-id";

export type VoiceRuntimeSwitchState = "idle" | "switching" | "ready" | "failed";

export type VoiceRuntimeTuple = {
  runtimeId: string;
  modelName: string;
};

export type VoiceRuntimeStateView = {
  selected: VoiceRuntimeTuple;
  active: VoiceRuntimeTuple;
  response: VoiceRuntimeTuple & {
    pipelineId: string;
    fresh: boolean;
    matchesActive: boolean | null;
  };
  switch: {
    state: VoiceRuntimeSwitchState;
    fromRuntime: string;
    toRuntime: string;
  };
};

type RuntimeSwitchGatePayload = {
  in_progress?: boolean;
  from_runtime?: string | null;
  to_runtime?: string | null;
  reason?: string | null;
} | null | undefined;

type LastRuntimeSwitchPayload = {
  at_utc?: string | null;
  from_runtime?: string | null;
  to_runtime?: string | null;
  reason?: string | null;
} | null | undefined;

type ActiveServerControlPayload = {
  active_server?: string | null;
  runtime_id?: string | null;
  active_model?: string | null;
  runtime_switch_gate?: RuntimeSwitchGatePayload;
  last_runtime_switch?: LastRuntimeSwitchPayload;
} | null;

type VoiceRuntimeStatePayload = {
  selected?: {
    runtime_id?: string | null;
    model_name?: string | null;
  } | null;
  active?: {
    runtime_id?: string | null;
    provider?: string | null;
    model_name?: string | null;
  } | null;
  response?: {
    provider?: string | null;
    model_name?: string | null;
    pipeline_id?: string | null;
    fresh?: boolean | null;
    matches_active?: boolean | null;
  } | null;
  switch?: {
    state?: string | null;
    from_runtime?: string | null;
    to_runtime?: string | null;
  } | null;
} | null;

type RuntimeSnapshotPayload = {
  runtime_id?: string | null;
  provider?: string | null;
  model_name?: string | null;
} | null;

type LatestSessionPayload = {
  audio_runtime_provider?: string | null;
  audio_runtime_model?: string | null;
  pipeline_id?: string | null;
} | null;

type RuntimeAlignmentPayload = {
  response_runtime_fresh?: boolean | null;
  response_runtime_matches_active?: boolean | null;
} | null;

type VoiceStatusPayload = {
  runtime_state?: VoiceRuntimeStatePayload;
  runtime_snapshot?: RuntimeSnapshotPayload;
  latest_voice_session?: LatestSessionPayload;
  runtime_alignment?: RuntimeAlignmentPayload;
} | null;

function coerce(value: string | null | undefined): string {
  return String(value ?? "").trim();
}

function tuple(runtimeId: string | null | undefined, modelName: string | null | undefined): VoiceRuntimeTuple {
  return {
    runtimeId: canonicalRuntimeId(coerce(runtimeId)),
    modelName: coerce(modelName),
  };
}

function normalizeSwitchState(value: string | null | undefined): VoiceRuntimeSwitchState {
  const normalized = coerce(value).toLowerCase();
  if (normalized === "switching") return "switching";
  if (normalized === "ready") return "ready";
  if (normalized === "failed") return "failed";
  return "idle";
}

function resolveSwitchStateFromServerControl(
  runtimeSwitchGate: RuntimeSwitchGatePayload,
  lastRuntimeSwitch: LastRuntimeSwitchPayload,
): VoiceRuntimeSwitchState {
  if (runtimeSwitchGate?.in_progress === true) return "switching";
  const reason = coerce(lastRuntimeSwitch?.reason).toLowerCase();
  if (reason && (reason.includes("error") || reason.includes("fail") || reason.includes("denied"))) {
    return "failed";
  }
  if (coerce(lastRuntimeSwitch?.at_utc) || coerce(lastRuntimeSwitch?.to_runtime)) {
    return "ready";
  }
  return "idle";
}

export function formatVoiceRuntimeTuple(runtime: string | null | undefined, model: string | null | undefined): string {
  const normalizedRuntime = canonicalRuntimeId(coerce(runtime));
  const normalizedModel = coerce(model);
  return `${normalizedRuntime || "—"} / ${normalizedModel || "—"}`;
}

export function buildVoiceRuntimeStateView(
  status: VoiceStatusPayload,
  selectedOverride?: VoiceRuntimeTuple,
): VoiceRuntimeStateView {
  const runtimeState = status?.runtime_state;
  const activeFromState = tuple(
    runtimeState?.active?.runtime_id ?? runtimeState?.active?.provider ?? null,
    runtimeState?.active?.model_name ?? null,
  );
  const activeFromSnapshot = tuple(
    status?.runtime_snapshot?.provider ?? status?.runtime_snapshot?.runtime_id ?? null,
    status?.runtime_snapshot?.model_name ?? null,
  );
  const active = activeFromState.runtimeId || activeFromState.modelName
    ? activeFromState
    : activeFromSnapshot;

  const selectedFromState = tuple(
    runtimeState?.selected?.runtime_id ?? null,
    runtimeState?.selected?.model_name ?? null,
  );
  const selectedFallback = selectedOverride ?? active;
  const selected = selectedFromState.runtimeId || selectedFromState.modelName
    ? selectedFromState
    : selectedFallback;

  const responseFromState = tuple(
    runtimeState?.response?.provider ?? null,
    runtimeState?.response?.model_name ?? null,
  );
  const responseFromSession = tuple(
    status?.latest_voice_session?.audio_runtime_provider ?? null,
    status?.latest_voice_session?.audio_runtime_model ?? null,
  );
  const responseTuple = responseFromState.runtimeId || responseFromState.modelName
    ? responseFromState
    : responseFromSession;
  const responsePipeline = coerce(
    runtimeState?.response?.pipeline_id ?? status?.latest_voice_session?.pipeline_id ?? null,
  );
  const responseFresh = runtimeState?.response?.fresh ?? status?.runtime_alignment?.response_runtime_fresh ?? false;
  const responseMatchesActive = runtimeState?.response?.matches_active
    ?? status?.runtime_alignment?.response_runtime_matches_active
    ?? null;

  const switchState = runtimeState?.switch ?? null;
  return {
    selected,
    active,
    response: {
      ...responseTuple,
      pipelineId: responsePipeline,
      fresh: Boolean(responseFresh),
      matchesActive: typeof responseMatchesActive === "boolean" ? responseMatchesActive : null,
    },
    switch: {
      state: normalizeSwitchState(switchState?.state),
      fromRuntime: canonicalRuntimeId(coerce(switchState?.from_runtime)),
      toRuntime: canonicalRuntimeId(coerce(switchState?.to_runtime)),
    },
  };
}

export function buildRuntimeStateViewFromActiveServer(
  activeServer: ActiveServerControlPayload,
  selectedOverride?: VoiceRuntimeTuple,
): VoiceRuntimeStateView {
  const runtimeSwitchGate = activeServer?.runtime_switch_gate;
  const lastRuntimeSwitch = activeServer?.last_runtime_switch;
  const active = tuple(
    activeServer?.active_server ?? activeServer?.runtime_id ?? null,
    activeServer?.active_model ?? null,
  );
  const selectedFromGate = tuple(
    runtimeSwitchGate?.to_runtime ?? lastRuntimeSwitch?.to_runtime ?? null,
    activeServer?.active_model ?? null,
  );
  const selected = selectedOverride
    ?? (selectedFromGate.runtimeId || selectedFromGate.modelName ? selectedFromGate : active);

  return {
    selected,
    active,
    response: {
      runtimeId: "",
      modelName: "",
      pipelineId: "",
      fresh: false,
      matchesActive: null,
    },
    switch: {
      state: resolveSwitchStateFromServerControl(runtimeSwitchGate, lastRuntimeSwitch),
      fromRuntime: canonicalRuntimeId(coerce(runtimeSwitchGate?.from_runtime ?? lastRuntimeSwitch?.from_runtime)),
      toRuntime: canonicalRuntimeId(coerce(runtimeSwitchGate?.to_runtime ?? lastRuntimeSwitch?.to_runtime)),
    },
  };
}
