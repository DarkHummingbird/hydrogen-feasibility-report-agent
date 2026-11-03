/** 与后端契约一致的类型（阶段 2 已验收，不改字段）。 */

export type ReportStatus = "draft" | "outline_ready" | "writing" | "paused" | "done";

export type ReportSummary = {
  id: string;
  title: string;
  target_words: number;
  status: ReportStatus;
  chapters_count: number;
  words_total: number;
  created_at: string;
};

export type Chapter = {
  id: number;
  seq: number;
  title: string;
  key_points: string[];
  data_needed: string[];
  suggested_words: number;
  status: string;
};

export type Report = {
  id: string;
  title: string;
  target_words: number;
  extra_requirements: string;
  status: ReportStatus;
  created_at: string;
  updated_at: string;
  chapters: Chapter[];
  warnings: string[];
};

export type CreateReportInput = {
  title: string;
  target_words: number;
  extra_requirements: string;
};

export type JobStatus = "pending" | "running" | "paused" | "succeeded" | "failed";

export type Job = {
  id: string;
  report_id: string;
  status: JobStatus;
  status_text: string;
  current_seq: number;
  total: number;
  message: string;
  error: string | null;
  notices: string[];
};

export type ProgressChapter = {
  seq: number;
  title: string;
  status: string;
  status_text: string;
  words: number;
  rewrite_count: number;
  truncated: boolean;
  critical_count: number;
  warning_count: number;
  missing: string[];
};

export type Progress = {
  report_id: string;
  report_status: ReportStatus;
  job: Job | null;
  chapters: ProgressChapter[];
  summary: { done: number; manual: number; failed: number; words_total: number };
};

export type DocumentStatus = "available" | "no_text" | "failed";

export type DocumentItem = {
  id: string;
  filename: string;
  status: DocumentStatus;
  segments_count: number;
  size_bytes: number;
  error: string | null;
  code: string | null;
  created_at: string;
};

export type OutlineChapterInput = {
  seq?: number;
  title: string;
  key_points: string[];
  data_needed: string[];
  suggested_words: number;
};
