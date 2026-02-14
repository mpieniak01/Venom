import { describe, it } from "node:test";
import { render, screen } from "@testing-library/react";
import { ProviderMetricsCard } from "../components/providers/provider-metrics-card";
import { ProviderHealthCard } from "../components/providers/provider-health-card";
import { AlertsList, AlertsSummary } from "../components/providers/alerts-list";

// Mock useTranslation hook
jest.mock("../lib/i18n", () => ({
  useTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) => {
      // Simple mock translation
      if (key.includes("noData")) return "No metrics data available";
      if (key.includes("title")) return "Provider Metrics";
      if (key.includes("healthScore")) return "Health Score";
      if (key.includes("totalRequests")) return "Total Requests";
      if (key.includes("successRate")) return "Success Rate";
      if (key.includes("latency.p50")) return "P50 Latency";
      if (key.includes("totalCost")) return "Total Cost";
      if (key.includes("totalTokens")) return "Total Tokens";
      if (key.includes("errorRate")) return "Error Rate";
      if (key.includes("availability")) return "Availability";
      if (key.includes("healthy")) return "Healthy";
      if (key.includes("degraded")) return "Degraded";
      if (key.includes("critical")) return "Critical";
      if (key.includes("noBreaches")) return "No SLO breaches";
      if (key.includes("sloBreaches")) return "SLO Breaches";
      if (key.includes("noAlerts")) return "No active alerts";
      if (key.includes("severity.warning")) return "Warning";
      if (key.includes("severity.critical")) return "Critical";
      if (key.includes("types.HIGH_LATENCY")) return "High Latency";
      
      // Handle parameterized messages
      if (params) {
        let result = key;
        Object.entries(params).forEach(([k, v]) => {
          result = result.replace(`{{${k}}}`, String(v));
        });
        return result;
      }
      
      return key;
    },
  }),
}));

describe("ProviderMetricsCard", () => {
  it("renders no data message when metrics is null", () => {
    render(<ProviderMetricsCard provider="openai" metrics={null} />);
    // @ts-expect-error - Testing library types
    expect(screen.getByText("No metrics data available")).toBeInTheDocument();
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
    
    expect(screen.getByText("1,000")).toBeInTheDocument(); // total requests
    expect(screen.getByText("95.0%")).toBeInTheDocument(); // success rate
    expect(screen.getByText("250ms")).toBeInTheDocument(); // p50
    expect(screen.getByText("500ms")).toBeInTheDocument(); // p95
    expect(screen.getByText("750ms")).toBeInTheDocument(); // p99
    expect(screen.getByText("$12.5000")).toBeInTheDocument(); // cost
    expect(screen.getByText("100,000")).toBeInTheDocument(); // tokens
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
    expect(dashElements).toHaveLength(3); // p50, p95, p99 all show —
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
    
    expect(screen.getByText("10")).toBeInTheDocument(); // total errors
    expect(screen.getByText("5")).toBeInTheDocument(); // timeouts
    expect(screen.getByText("3")).toBeInTheDocument(); // auth errors
    expect(screen.getByText("2")).toBeInTheDocument(); // budget errors
  });
});

describe("ProviderHealthCard", () => {
  it("renders no data message when health is null", () => {
    render(<ProviderHealthCard provider="openai" health={null} />);
    expect(screen.getByText("No metrics data available")).toBeInTheDocument();
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
    
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.getByText("100/100")).toBeInTheDocument();
    expect(screen.getByText("No SLO breaches")).toBeInTheDocument();
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
    
    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText("75/100")).toBeInTheDocument();
    expect(screen.getByText("latency_p99_1500ms_above_1000ms")).toBeInTheDocument();
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
    
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("20/100")).toBeInTheDocument();
    
    // Check all breaches are displayed
    expect(screen.getByText(/availability.*90.*99/)).toBeInTheDocument();
    expect(screen.getByText(/latency.*3000.*1000/)).toBeInTheDocument();
    expect(screen.getByText(/error_rate.*5\.0.*1\.0/)).toBeInTheDocument();
    expect(screen.getByText(/cost.*60.*50/)).toBeInTheDocument();
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
    
    expect(screen.getByText(/99\.80% \/ 99\.00%/)).toBeInTheDocument(); // availability
    expect(screen.getByText(/500ms \/ 1000ms/)).toBeInTheDocument(); // latency
    expect(screen.getByText(/0\.20% \/ 1\.00%/)).toBeInTheDocument(); // error rate
    expect(screen.getByText(/\$15\.00 \/ \$50\.00/)).toBeInTheDocument(); // cost
  });
});

describe("AlertsList", () => {
  it("renders no alerts message when empty", () => {
    render(<AlertsList alerts={[]} />);
    expect(screen.getByText("No active alerts")).toBeInTheDocument();
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
    
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("Warning")).toBeInTheDocument();
    expect(screen.getByText("High Latency")).toBeInTheDocument();
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("google")).toBeInTheDocument();
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
    
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.queryByText("google")).not.toBeInTheDocument();
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
    
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.queryByText("Warning")).not.toBeInTheDocument();
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
    
    expect(screen.getByText("10")).toBeInTheDocument(); // total
    expect(screen.getByText("3")).toBeInTheDocument(); // info
    expect(screen.getByText("5")).toBeInTheDocument(); // warning
    expect(screen.getByText("2")).toBeInTheDocument(); // critical
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("google")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
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
    expect(zeros.length).toBeGreaterThanOrEqual(4); // total + 3 severities
  });
});
