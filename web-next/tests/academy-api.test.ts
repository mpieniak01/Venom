import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { uploadDatasetFiles } from "../lib/academy-api";

describe("academy api upload error parser", () => {
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
});
