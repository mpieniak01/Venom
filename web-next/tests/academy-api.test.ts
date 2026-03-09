import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveAcademyApiErrorMessage, uploadDatasetFiles } from "../lib/academy-api";
import { ApiError } from "../lib/api-client";

describe("academy api helpers", () => {
  it("formats structured validation detail with requested context", () => {
    const error = new ApiError("Request failed: 400", 400, {
      detail: {
        message: "Model is incompatible with runtime.",
        requested_runtime_id: "ollama",
        requested_base_model: "gemma-3-4b-it",
      },
    });

    assert.equal(
      resolveAcademyApiErrorMessage(error),
      "Model is incompatible with runtime. (runtime=ollama, base_model=gemma-3-4b-it)",
    );
  });

  it("formats structured validation detail with compatible runtimes context", () => {
    const error = new ApiError("Request failed: 400", 400, {
      detail: {
        message: "Model is incompatible with runtime.",
        requested_runtime_id: "ollama",
        requested_base_model: "unsloth/Phi-3-mini-4k-instruct",
        compatible_runtimes: ["vllm"],
      },
    });

    assert.equal(
      resolveAcademyApiErrorMessage(error),
      "Model is incompatible with runtime. (runtime=ollama, base_model=unsloth/Phi-3-mini-4k-instruct, compatible_runtimes=vllm)",
    );
  });

  it("formats adapter activation validation detail with adapter and runtime model context", () => {
    const error = new ApiError("Request failed: 400", 400, {
      detail: {
        message: "Adapter base model does not match selected runtime model.",
        adapter_id: "self_learning_gemma",
        requested_runtime_id: "ollama",
        requested_model_id: "phi3:mini",
      },
    });

    assert.equal(
      resolveAcademyApiErrorMessage(error),
      "Adapter base model does not match selected runtime model. (adapter=self_learning_gemma, runtime=ollama, model_id=phi3:mini)",
    );
  });

  it("formats structured internal training error with requested runtime and base model context", () => {
    const error = new ApiError("Request failed: 500", 500, {
      detail: {
        message: "Failed to start training: boom",
        requested_runtime_id: "ollama",
        requested_base_model: "gemma-3-4b-it",
      },
    });

    assert.equal(
      resolveAcademyApiErrorMessage(error),
      "Failed to start training: boom (runtime=ollama, base_model=gemma-3-4b-it)",
    );
  });

  it("formats structured dataset curation error without extra context noise", () => {
    const error = new ApiError("Request failed: 500", 500, {
      detail: {
        message: "Failed to curate dataset: curate internal error",
        reason_code: "DATASET_CURATE_FAILED",
      },
    });

    assert.equal(
      resolveAcademyApiErrorMessage(error),
      "Failed to curate dataset: curate internal error",
    );
  });

  it("formats structured error with only compatible runtimes", () => {
    const error = new ApiError("Request failed: 400", 400, {
      detail: {
        message: "No compatible runtime targets.",
        compatible_runtimes: ["vllm", "ollama"],
      },
    });

    assert.equal(
      resolveAcademyApiErrorMessage(error),
      "No compatible runtime targets. (compatible_runtimes=vllm|ollama)",
    );
  });

  it("surfaces FastAPI detail string from JSON body", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ detail: "Invalid file format" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });

    try {
      const file = new Blob(["demo"], { type: "text/plain" }) as unknown as File;
      await assert.rejects(
        () => uploadDatasetFiles({ files: [file] }),
        (error: unknown) => {
          assert.equal((error as Error).message, "Invalid file format");
          return true;
        }
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("returns empty string when academy error cannot be resolved", () => {
    assert.equal(resolveAcademyApiErrorMessage(null), "");
  });
});
