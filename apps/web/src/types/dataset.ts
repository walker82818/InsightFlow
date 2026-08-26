export type DatasetType =
  | "string"
  | "integer"
  | "float"
  | "date"
  | "category"
  | "boolean";

export interface DatasetColumn {
  name: string;
  type: DatasetType;
  position: number;
  stats: Record<string, unknown>;
}

export interface DbInfo {
  db_type: string;
  host?: string | null;
  port?: number | null;
  database?: string | null;
  schema?: string | null;
  table: string;
}

export interface DatasetSummary {
  id: string;
  name: string;
  file_name: string;
  file_type: string;
  file_size: number;
  row_count: number;
  column_count: number;
  status: string;
  created_at: string;
  columns: DatasetColumn[];
  source_type?: string;
  db_info?: DbInfo | null;
}

export interface DatasetProfile {
  row_count: number;
  column_count: number;
  duplicate_rows: number;
  total_missing: number;
  missing_ratio: number;
}

export interface DatasetDetail extends DatasetSummary {
  profile: DatasetProfile;
  preview: Record<string, unknown>[];
}
