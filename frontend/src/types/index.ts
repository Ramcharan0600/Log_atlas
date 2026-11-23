export type Job = {
  id: number; filename: string; dataset_name?: string | null; is_synthetic: boolean; status: "queued" | "running" | "completed" | "failed";
  progress: number; stage: string; error?: string | null; total_logs: number; config: Record<string, any>; stats: Record<string, any>;
  created_at: string; started_at?: string | null; completed_at?: string | null;
};
export type ClusterBrief = {
  id: number; local_id: number; name: string; size: number; severity: string; priority: string; priority_score: number; first_seen?: string | null;
  last_seen?: string | null; is_anomalous: boolean; keywords: string[]; services: Record<string, number>; template?: string; summary: string; trend_ratio?: number;
};
export type ClusterDetail = ClusterBrief & {
  representatives: string[]; levels: Record<string, number>; trend: { t: string; count: number }[]; related: { id: number; name: string; similarity: number }[];
  priority_factors: Record<string, number>; priority_explanation?: string; summary_source: string; n_unique_messages?: number; anomalies: Anomaly[];
};
export type Anomaly = {
  id: number; kind: string; score: number; reason: string; detected_at?: string | null; cluster?: number | null; cluster_name?: string | null;
  severity: string; impact: string; n_logs: number;
};
export type AnomalyDetail = Anomaly & { trend: { t: string; count: number }[]; logs: LogRow[] };
export type LogRow = {
  id: number; line_no: number; timestamp?: string | null; severity: string; service?: string | null; component?: string | null; host?: string | null; ip?: string | null;
  pid?: string | null; thread?: string | null; request_id?: string | null; error_code?: string | null; original_message: string; normalized_message: string;
  template_id?: number | null; template?: string | null; cluster_id?: number | null; cluster_pk?: number | null; cluster_name?: string | null; anomaly_flag: boolean; anomaly_score: number;
};
export type Page<T> = { total: number; page?: number; page_size?: number; items: T[] };
export type Insight = {
  id: number; title: string; hypothesis: string; summary: string; evidence: { type: string; text: string }[]; suspected_causes: string[]; recommendations: string[];
  confidence: string; timeline: { time: string; event: string }[]; disclaimer: string; cluster?: number | null; related_clusters: { id: number; name: string }[];
};
export type Summary = {
  job: Job; total_logs: number; n_clusters: number; critical: number; anomalies: number; n_templates: number; levels: Record<string, number>; services: Record<string, number>;
  error_services: Record<string, number>; time_range: string[]; top_clusters: ClusterBrief[]; recent_anomalies: Anomaly[]; recent_jobs: Job[]; is_synthetic: boolean;
};
export type Timeline = { freq: string | null; points: { t: string; total: number; errors: number; anomalies: number }[] };
export type GridRow = {
  features: string; feature_backend: string; algorithm: string; parameters?: Record<string, any>; metrics?: Record<string, number>;
  cluster_seconds?: number; feature_seconds?: number; peak_memory_mb?: number; error?: string;
};
export type Evaluation = {
  evaluation: {
    final?: Record<string, number>; final_after_noise_attachment?: Record<string, number>; feature_backend?: string; feature_note?: string; timings_s?: Record<string, number>;
    total_seconds?: number; logs_per_second?: number; has_cluster_labels?: boolean; has_anomaly_labels?: boolean; clustering_used?: Record<string, any>; raw_noise_ratio?: number;
    template_methods?: Record<string, Record<string, number>>; template_grouping_accuracy?: number;
    comparison?: { grid: GridRow[]; note?: string | null; warning?: string; supervised: boolean; evaluated_unique_messages: number; evaluated_logs: number };
    anomaly?: Record<string, Record<string, number>>; anomaly_note?: string;
  };
  is_synthetic: boolean; dataset: string; config: Record<string, any>;
  experiments: { id: number; kind: string; algorithm: string; features: string; parameters: Record<string, any>; metrics: Record<string, any>; execution_time: number; created_at: string }[];
};
export type DatasetInfo = {
  name: string; source: string; is_synthetic: boolean; license: string; labels: string; format: string; lines?: number | null; description: string;
  loaded_file_id?: number | null; available_offline: boolean;
};
export type Preview = {
  filename: string; encoding: string; detected_format: string; n_records: number; invalid_lines: number; timestamp_parse_rate: number;
  level_distribution_sample: Record<string, number>; has_ground_truth: boolean; rows: { line_no: number; timestamp?: string | null; level: string; service?: string | null; message: string }[];
};
export type UploadedItem = { file_id?: number; filename: string; size_bytes?: number; preview?: Preview; error?: string; dataset_name?: string | null; is_synthetic?: boolean };
