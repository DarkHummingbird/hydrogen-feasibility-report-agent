import { request } from "./client";
import type {
  CreateReportInput,
  OutlineChapterInput,
  Progress,
  Report,
  ReportSummary,
} from "./types";

export function listReports() {
  return request<{ items: ReportSummary[] }>("/api/reports");
}

export function getReport(id: string) {
  return request<Report>(`/api/reports/${id}`);
}

export function createReport(input: CreateReportInput) {
  return request<Report>("/api/reports", { method: "POST", json: input });
}

export function deleteReport(id: string) {
  return request<{ deleted: boolean }>(`/api/reports/${id}`, { method: "DELETE" });
}

export function getProgress(id: string) {
  return request<Progress>(`/api/reports/${id}/progress`);
}

export function generateOutline(id: string) {
  return request<Report>(`/api/reports/${id}/outline`, { method: "POST" });
}

export function saveOutline(id: string, chapters: OutlineChapterInput[]) {
  return request<Report>(`/api/reports/${id}/outline`, {
    method: "PUT",
    json: { chapters },
  });
}

export function confirmOutline(id: string) {
  return request<{ id: string; status: string; status_text: string; message: string }>(
    `/api/reports/${id}/outline/confirm`,
    { method: "POST" },
  );
}
