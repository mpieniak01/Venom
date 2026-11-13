export const DATA_AUDIT = "academy.experiments.dataAudit.";

export type DataAuditGroup = "replay" | "fresh";

export interface DataAuditCounts {
  records: number;
  supervised_tokens: number;
  input_tokens: number;
  max_input_tokens: number;
  max_supervised_tokens: number;
}

interface DataAuditMinimum {
  min_records?: number;
  min_supervised_tokens?: number;
}

interface DataAuditEvidence {
  report_sha256: string;
  report: {
    schema_version: 1;
    model: string;
    revision: string;
    snapshot_sha256: string;
    train_sha256: string;
    dev_sha256: string;
    taxonomy_sha256: string;
    tokenization: {
      template_sha256: string;
      tokenizer_sha256: string;
      tokenizer_config_sha256: string;
      model_config_sha256: string;
      transformers: string;
      tokenizers: string;
      max_tokens: number;
    };
    totals: DataAuditCounts;
    groups: Record<DataAuditGroup, DataAuditCounts>;
    skills: Record<string, Record<DataAuditGroup, DataAuditCounts>>;
    leakage: {
      normalization: "nfkc_casefold_whitespace_v1";
      supervised_prefix_matches: number;
      final_user_matches: number;
      duplicate_train_records: number;
    };
  };
  policy: {
    groups: Partial<Record<DataAuditGroup, DataAuditMinimum>>;
    skills: Record<string, Partial<Record<DataAuditGroup, DataAuditMinimum>>>;
  };
}

export type PassedDataAudit = DataAuditEvidence & { status: "passed" };

interface DataAuditViolation {
  group: DataAuditGroup;
  skill?: string;
  metric: "records" | "supervised_tokens";
  actual: number;
  minimum: number;
}

export type DataAudit = PassedDataAudit | (Partial<DataAuditEvidence> & {
  status: "blocked";
  error: string;
  violations?: DataAuditViolation[];
});

export function dataAuditErrorKey(code?: string | null) {
  return code?.startsWith("experiment_data_audit_") ? DATA_AUDIT + "errors." + code : undefined;
}
