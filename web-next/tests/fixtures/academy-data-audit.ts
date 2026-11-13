import type { DataAuditCounts, PassedDataAudit } from "../../lib/academy-data-audit";

function counts(records: number, supervisedTokens: number, inputTokens: number, maxInput: number, maxSupervised: number): DataAuditCounts {
  return {
    records,
    supervised_tokens: supervisedTokens,
    input_tokens: inputTokens,
    max_input_tokens: maxInput,
    max_supervised_tokens: maxSupervised,
  };
}

export function auditFixture(model = "Omni"): PassedDataAudit {
  return {
    status: "passed",
    report_sha256: "d".repeat(64),
    policy: {
      groups: { replay: { min_records: 2 } },
      skills: { state_update: { replay: { min_records: 1 } } },
    },
    report: {
      schema_version: 1,
      model,
      revision: "e".repeat(40),
      snapshot_sha256: "b".repeat(64),
      train_sha256: "c".repeat(64),
      dev_sha256: "e".repeat(64),
      taxonomy_sha256: "f".repeat(64),
      tokenization: {
        template_sha256: "1".repeat(64),
        tokenizer_sha256: "2".repeat(64),
        tokenizer_config_sha256: "3".repeat(64),
        model_config_sha256: "4".repeat(64),
        transformers: "5.0.0",
        tokenizers: "0.22.0",
        max_tokens: 1280,
      },
      totals: counts(12, 100, 300, 70, 20),
      groups: { replay: counts(9, 40, 180, 70, 15), fresh: counts(3, 60, 120, 65, 20) },
      skills: {
        state_update: { replay: counts(9, 40, 180, 70, 15), fresh: counts(0, 0, 0, 0, 0) },
        dialogue: { replay: counts(0, 0, 0, 0, 0), fresh: counts(3, 60, 120, 65, 20) },
      },
      leakage: {
        normalization: "nfkc_casefold_whitespace_v1",
        supervised_prefix_matches: 0,
        final_user_matches: 0,
        duplicate_train_records: 0,
      },
    },
  };
}

export function blockedAuditFixture(model = "Omni") {
  const audit = auditFixture(model);
  return {
    ...audit,
    status: "blocked",
    error: "experiment_data_audit_threshold",
    violations: [{ group: "replay", skill: "state_update", metric: "records", actual: 9, minimum: 10 }],
    policy: { ...audit.policy, skills: { state_update: { replay: { min_records: 10 } } } },
  } as const;
}
