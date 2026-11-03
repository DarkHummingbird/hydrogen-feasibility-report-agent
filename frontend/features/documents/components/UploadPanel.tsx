"use client";

import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { uploadDocuments } from "@/lib/api/documents";
import { isAppError } from "@/lib/api/client";
import type { DocumentItem } from "@/lib/api/types";

const ACCEPT = ".pdf,.docx,.md,.txt";
const MAX_MB = 100;

export function UploadPanel({ onUploaded }: { onUploaded: (items: DocumentItem[]) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = () => inputRef.current?.click();

  const submit = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const list = Array.from(files);
    const tooBig = list.filter((f) => f.size > MAX_MB * 1024 * 1024);
    if (tooBig.length) {
      setError(`超过 ${MAX_MB} MB：${tooBig.map((f) => f.name).join("、")}`);
      return;
    }
    setBusy(true);
    setError("");
    setResult("");
    try {
      const data = await uploadDocuments(list);
      const failed = data.items.filter((i) => i.status === "failed");
      const noText = data.items.filter((i) => i.status === "no_text");
      const parts = [`${data.items.length} 份已处理`];
      if (noText.length) parts.push(`${noText.length} 份无文字（扫描件？）`);
      if (failed.length) parts.push(`${failed.length} 份失败`);
      setResult(parts.join("，"));
      if (failed.length) setError(failed.map((f) => `${f.filename}：${f.error}`).join("\n"));
      onUploaded(data.items);
    } catch (err) {
      setError(isAppError(err) ? err.userMessage : "上传失败，请稍后重试");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div>
      <div
        className="flex flex-col items-center gap-2 rounded-card border border-dashed border-hairline bg-canvas/60 px-6 py-8 text-center"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          void submit(event.dataTransfer.files);
        }}
      >
        <UploadCloud className="h-5 w-5 text-ink-muted" aria-hidden />
        <p className="text-[13px] text-ink">把文件拖到这里，或点下面的按钮选择</p>
        <p className="text-[12px] text-ink-muted">
          支持 PDF、Word（.docx）、Markdown、TXT；单个 ≤ {MAX_MB} MB，可一次选多个。扫描件会被标为「无文字，检索不到」。
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(event) => void submit(event.target.files)}
        />
        <div className="mt-1">
          <Button onClick={pick} disabled={busy}>
            {busy ? "正在上传…" : "选择文件"}
          </Button>
        </div>
      </div>
      {result ? <p className="mt-2 text-[12px] text-ink-muted">{result}</p> : null}
      {error ? (
        <p role="alert" className="mt-2 whitespace-pre-wrap text-[12px] text-vermillion">
          {error}
        </p>
      ) : null}
    </div>
  );
}
