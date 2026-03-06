import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, render, screen } from "@testing-library/react";
import { ProviderMetricsCard } from "../components/providers/provider-metrics-card";
import { ProviderHealthCard } from "../components/providers/provider-health-card";
import { AlertsList, AlertsSummary } from "../components/providers/alerts-list";

afterEach(() => {
  cleanup();
});

function assertTextVisible(text: string | RegExp) {
  assert.ok(screen.queryAllByText(text).length > 0);
}

function assertTextMissing(text: string | RegExp) {
  assert.equal(screen.queryAllByText(text).length, 0);
}

describe("ProviderMetricsCard", () => {
  it("renders no data message when metrics is null", () => {
    render(<ProviderMetricsCard provider="openai" metrics={null} />);
    assertTextVisible("Brak danych metryk");
  });

  it("renders metrics with all data", () => {
    const metrics = {
      total_requests: 1000,
      successful_requests: 950,
      failed_requests: 50,
      success_rate: 95.0,
      error_rate: 5.0,
      latency: {
        p50_ms: 250,
        p95_ms: 500,
        p99_ms: 750,
        samples: 1000,
      },
      errors: {
        total: 50,
        timeouts: 10,
        auth_errors: 5,
        budget_errors: 2,
        by_code: { TIMEOUT: 10, AUTH_ERROR: 5 },
      },
      cost: {
        total_usd: 12.5,
        total_tokens: 100000,
      },
    };

    render(<ProviderMetricsCard provider="openai" metrics={metrics} />);

    assertTextVisible("1,000"); // total requests
    assertTextVisible("95.0%"); // success rate
    assertTextVisible("250ms"); // p50
    assertTextVisible("500ms"); // p95
    assertTextVisible("750ms"); // p99
    assertTextVisible("$12.5000"); // cost
    assertTextVisible("100,000"); // tokens
  });

  it("handles missing latency data", () => {
    const metrics = {
      total_requests: 10,
      successful_requests: 10,
      failed_requests: 0,
      success_rate: 100.0,
      error_rate: 0.0,
      latency: {
        p50_ms: null,
        p95_ms: null,
        p99_ms: null,
        samples: 0,
      },
      errors: {
        total: 0,
        timeouts: 0,
        auth_errors: 0,
        budget_errors: 0,
        by_code: {},
      },
      cost: {
        total_usd: 0,
        total_tokens: 0,
      },
    };

    render(<ProviderMetricsCard provider="ollama" metrics={metrics} />);

    const dashElements = screen.getAllByText("—");
    assert.equal((dashElements).length, 3); // p50, p95, p99 all show —
  });

  it("shows error breakdown when errors exist", () => {
    const metrics = {
      total_requests: 100,
      successful_requests: 90,
      failed_requests: 10,
      success_rate: 90.0,
      error_rate: 10.0,
      latency: {
        p50_ms: 200,
        p95_ms: 400,
        p99_ms: 600,
        samples: 100,
      },
      errors: {
        total: 10,
        timeouts: 5,
        auth_errors: 3,
        budget_errors: 2,
        by_code: { TIMEOUT: 5, AUTH_ERROR: 3, BUDGET_EXCEEDED: 2 },
      },
      cost: {
        total_usd: 1.0,
        total_tokens: 10000,
      },
    };

    render(<ProviderMetricsCard provider="openai" metrics={metrics} />);

    assertTextVisible("10"); // total errors
    assertTextVisible("5"); // timeouts
    assertTextVisible("3"); // auth errors
    assertTextVisible("2"); // budget errors
  });
});

describe("ProviderHealthCard", () => {
  it("renders no data message when health is null", () => {
    render(<ProviderHealthCard provider="openai" health={null} />);
    assertTextVisible("Brak danych metryk");
  });

  it("renders healthy status correctly", () => {
    const health = {
      health_status: "healthy" as const,
      health_score: 100,
      availability: 0.995,
      latency_p99_ms: 800,
      error_rate: 0.005,
      cost_usage_usd: 10.0,
      slo_target: {
        availability_target: 0.99,
        latency_p99_ms: 1000,
        error_rate_target: 0.01,
        cost_budget_usd: 50.0,
      },
      slo_breaches: [],
    };

    render(<ProviderHealthCard provider="openai" health={health} />);

    assertTextVisible("Zdrowy");
    assertTextVisible("100/100");
    assertTextVisible("Brak naruszeń SLO");
  });

  it("renders degraded status with breaches", () => {
    const health = {
      health_status: "degraded" as const,
      health_score: 75,
      availability: 0.98,
      latency_p99_ms: 1500,
      error_rate: 0.008,
      cost_usage_usd: 45.0,
      slo_target: {
        availability_target: 0.99,
        latency_p99_ms: 1000,
        error_rate_target: 0.01,
        cost_budget_usd: 50.0,
      },
      slo_breaches: ["latency_p99_1500ms_above_1000ms"],
    };

    render(<ProviderHealthCard provider="google" health={health} />);

    assertTextVisible("Ograniczony");
    assertTextVisible("75/100");
    assertTextVisible("latency_p99_1500ms_above_1000ms");
  });

  it("renders critical status with multiple breaches", () => {
    const health = {
      health_status: "critical" as const,
      health_score: 20,
      availability: 0.90,
      latency_p99_ms: 3000,
      error_rate: 0.05,
      cost_usage_usd: 60.0,
      slo_target: {
        availability_target: 0.99,
        latency_p99_ms: 1000,
        error_rate_target: 0.01,
        cost_budget_usd: 50.0,
      },
      slo_breaches: [
        "availability_90.0%_below_99.0%",
        "latency_p99_3000ms_above_1000ms",
        "error_rate_5.0%_above_1.0%",
        "cost_$60.00_above_$50.00",
      ],
    };

    render(<ProviderHealthCard provider="openai" health={health} />);

    assertTextVisible("Krytyczny");
    assertTextVisible("20/100");

    // Check all breaches are displayed
    assertTextVisible(/availability.*90.*99/);
    assertTextVisible(/latency.*3000.*1000/);
    assertTextVisible(/error_rate.*5\.0.*1\.0/);
    assertTextVisible(/cost.*60.*50/);
  });

  it("shows SLO targets vs current metrics", () => {
    const health = {
      health_status: "healthy" as const,
      health_score: 95,
      availability: 0.998,
      latency_p99_ms: 500,
      error_rate: 0.002,
      cost_usage_usd: 15.0,
      slo_target: {
        availability_target: 0.99,
        latency_p99_ms: 1000,
        error_rate_target: 0.01,
        cost_budget_usd: 50.0,
      },
      slo_breaches: [],
    };

    render(<ProviderHealthCard provider="openai" health={health} />);

    assertTextVisible(/99\.80% \/ 99\.00%/); // availability
    assertTextVisible(/500ms \/ 1000ms/); // latency
    assertTextVisible(/0\.20% \/ 1\.00%/); // error rate
    assertTextVisible(/\$15\.00 \/ \$50\.00/); // cost
  });
});

describe("AlertsList", () => {
  it("renders no alerts message when empty", () => {
    render(<AlertsList alerts={[]} />);
    assertTextVisible("Brak aktywnych alertów");
  });

  it("renders alerts with correct severity colors and icons", () => {
    const alerts = [
      {
        id: "1",
        severity: "critical" as const,
        alert_type: "HIGH_LATENCY",
        provider: "openai",
        message: "High latency detected",
        technical_details: "p99=2500ms threshold=1000ms",
        timestamp: new Date().toISOString(),
        expires_at: null,
        metadata: { latency: 2500, threshold: 1000 },
      },
      {
        id: "2",
        severity: "warning" as const,
        alert_type: "ERROR_SPIKE",
        provider: "google",
        message: "Error spike detected",
        technical_details: null,
        timestamp: new Date().toISOString(),
        expires_at: null,
        metadata: { rate: 5 },
      },
    ];

    render(<AlertsList alerts={alerts} />);

    assertTextVisible("Krytyczny");
    assertTextVisible("Ostrzeżenie");
    assertTextVisible("Wysokie Opóźnienie");
    assertTextVisible("openai");
    assertTextVisible("google");
  });

  it("filters alerts by provider", () => {
    const alerts = [
      {
        id: "1",
        severity: "warning" as const,
        alert_type: "HIGH_LATENCY",
        provider: "openai",
        message: "test",
        technical_details: null,
        timestamp: new Date().toISOString(),
        expires_at: null,
        metadata: {},
      },
      {
        id: "2",
        severity: "warning" as const,
        alert_type: "ERROR_SPIKE",
        provider: "google",
        message: "test",
        technical_details: null,
        timestamp: new Date().toISOString(),
        expires_at: null,
        metadata: {},
      },
    ];

    render(<AlertsList alerts={alerts} providerFilter="openai" />);

    assertTextVisible("openai");
    assertTextMissing("google");
  });

  it("filters alerts by severity", () => {
    const alerts = [
      {
        id: "1",
        severity: "critical" as const,
        alert_type: "HIGH_LATENCY",
        provider: "openai",
        message: "test",
        technical_details: null,
        timestamp: new Date().toISOString(),
        expires_at: null,
        metadata: {},
      },
      {
        id: "2",
        severity: "warning" as const,
        alert_type: "ERROR_SPIKE",
        provider: "openai",
        message: "test",
        technical_details: null,
        timestamp: new Date().toISOString(),
        expires_at: null,
        metadata: {},
      },
    ];

    render(<AlertsList alerts={alerts} severityFilter="critical" />);

    assertTextVisible("Krytyczny");
    assertTextMissing("Ostrzeżenie");
  });
});

describe("AlertsSummary", () => {
  it("renders summary with all counts", () => {
    const summary = {
      total_active: 10,
      by_severity: {
        info: 3,
        warning: 5,
        critical: 2,
      },
      by_provider: {
        openai: 6,
        google: 4,
      },
    };

    render(<AlertsSummary summary={summary} />);

    assertTextVisible("10"); // total
    assertTextVisible("3"); // info
    assertTextVisible("5"); // warning
    assertTextVisible("2"); // critical
    assertTextVisible("openai");
    assertTextVisible("6");
    assertTextVisible("google");
    assertTextVisible("4");
  });

  it("renders with zero alerts", () => {
    const summary = {
      total_active: 0,
      by_severity: {
        info: 0,
        warning: 0,
        critical: 0,
      },
      by_provider: {},
    };

    render(<AlertsSummary summary={summary} />);

    const zeros = screen.getAllByText("0");
    assert.ok((zeros.length) >= 4); // total + 3 severities
  });
});
