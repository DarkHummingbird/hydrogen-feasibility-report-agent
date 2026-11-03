import { request } from "./client";
import type { DocumentItem } from "./types";

export function listDocuments() {
  return request<{ items: DocumentItem[] }>("/api/documents");
}

export function uploadDocuments(files: File[]) {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return request<{ items: DocumentItem[] }>("/api/documents", { method: "POST", body: form });
}

export function deleteDocument(id: string) {
  return request<{ deleted: boolean }>(`/api/documents/${id}`, { method: "DELETE" });
}
