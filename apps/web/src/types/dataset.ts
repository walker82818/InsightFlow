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
