import { describe, it } from "node:test";
import assert from "node:assert";
import { shouldShowConnection, type ApiConnection } from "../components/config/api-map";

describe("ApiMap Filtering Logic", () => {
    // Base connection object to reduce boilerplate
    const baseConn: ApiConnection = {
        target_component: "Test Target",
        source_component: "Test Source",
        methods: [],
        auth_type: "none",
        description: "Test Description",
        direction: "bidirectional",
        is_critical: false,
        status: "ok",
        source_type: "local",
        protocol: "http"
    };

    it("should return true when all filters are 'all'", () => {
        const conn = { ...baseConn, source_type: "cloud", status: "ok", protocol: "http" } as ApiConnection;
        const filters = { source: "all", status: "all", protocol: "all" };
        assert.strictEqual(shouldShowConnection(conn, filters), true);
    });

    it("should filter by source", () => {
        const conn = { ...baseConn, source_type: "cloud", status: "ok", protocol: "http" } as ApiConnection;

        // Match
        assert.strictEqual(shouldShowConnection(conn, { source: "cloud", status: "all", protocol: "all" }), true);

        // Mismatch
        assert.strictEqual(shouldShowConnection(conn, { source: "local", status: "all", protocol: "all" }), false);
    });

    it("should filter by status", () => {
        const conn = { ...baseConn, source_type: "cloud", status: "down", protocol: "http" } as ApiConnection;

        // Match
        assert.strictEqual(shouldShowConnection(conn, { source: "all", status: "down", protocol: "all" }), true);

        // Mismatch
        assert.strictEqual(shouldShowConnection(conn, { source: "all", status: "ok", protocol: "all" }), false);
    });

    it("should filter by protocol", () => {
        const conn = { ...baseConn, source_type: "cloud", status: "ok", protocol: "ws" } as ApiConnection;

        // Match
        assert.strictEqual(shouldShowConnection(conn, { source: "all", status: "all", protocol: "ws" }), true);

        // Mismatch
        assert.strictEqual(shouldShowConnection(conn, { source: "all", status: "all", protocol: "http" }), false);
    });

    it("should filter by multiple criteria", () => {
        const conn = { ...baseConn, source_type: "local", status: "degraded", protocol: "http" } as ApiConnection;

        // Match all
        assert.strictEqual(shouldShowConnection(conn, { source: "local", status: "degraded", protocol: "http" }), true);

        // Mismatch one
        assert.strictEqual(shouldShowConnection(conn, { source: "local", status: "ok", protocol: "http" }), false);
    });
});
