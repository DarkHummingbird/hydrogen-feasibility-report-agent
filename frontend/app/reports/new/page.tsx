"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card, CardTitle } from "@/components/ui/Card";
import { ErrorText, Hint, Input, Label, Textarea } from "@/components/ui/Field";
import { createReport } from "@/lib/api/reports";
import { isAppError } from "@/lib/api/client";

const TARGET_MAX = 18000;
const TARGET_MIN = 1000;

export default function NewReportPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [targetWords, setTargetWords] = useState(12000);
  const [requirements, setRequirements] = useState("");
  const [errors, setErrors] = useState<{ title?: string; targetWords?: string; requirements?: string }>({});
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const validate = () => {
    const next: typeof errors = {};
    if (!title.trim()) next.title = "请填写报告标题（例如：××项目可行性研究报告）";
    if (Number.isNaN(targetWords) || targetWords < TARGET_MIN || targetWords > TARGET_MAX) {
      next.targetWords = `全文不能超过 2 万字，目标字数只能填 ${TARGET_MIN} 到 ${TARGET_MAX}`;
    }
    if (requirements.length > 2000) next.requirements = "补充要求最多 2,000 字";
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError("");
    if (!validate()) return;
    setSubmitting(true);
    try {
      await createReport({
        title: title.trim(),
        target_words: targetWords,
        extra_requirements: requirements.trim(),
      });
      router.push("/?created=1");
    } catch (err) {
      setFormError(isAppError(err) ? err.userMessage : "创建失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div>
        <h1 className="display text-ink">创建报告</h1>
        <p className="mt-1 text-[13px] text-ink-muted">只需要三项：标题、目标字数、补充要求（可空）。</p>
      </div>

      <Card>
        <CardTitle>报告设置</CardTitle>
        <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
          <div>
            <Label htmlFor="title">报告标题</Label>
            <Input
              id="title"
              value={title}
              invalid={Boolean(errors.title)}
              placeholder="××市××制氢加氢一体化示范项目（一期）可行性研究报告"
              onChange={(e) => setTitle(e.target.value)}
            />
            {errors.title ? <ErrorText>{errors.title}</ErrorText> : null}
          </div>

          <div>
            <Label htmlFor="target-words">目标字数</Label>
            <Input
              id="target-words"
              type="number"
              min={TARGET_MIN}
              max={TARGET_MAX}
              step={1000}
              value={targetWords}
              invalid={Boolean(errors.targetWords)}
              onChange={(e) => setTargetWords(Number(e.target.value))}
            />
            {errors.targetWords ? (
              <ErrorText>{errors.targetWords}</ErrorText>
            ) : (
              <Hint>默认 12,000 字，最多 18,000 字（全文必须不到 2 万字）。</Hint>
            )}
          </div>

          <div>
            <Label htmlFor="requirements">补充要求（可空）</Label>
            <Textarea
              id="requirements"
              value={requirements}
              invalid={Boolean(errors.requirements)}
              placeholder="例如：重点写清楚投资构成和电价敏感性"
              onChange={(e) => setRequirements(e.target.value)}
            />
            {errors.requirements ? (
              <ErrorText>{errors.requirements}</ErrorText>
            ) : (
              <Hint>最多 2,000 字。与项目资料冲突的要求不会被照抄，正文会按资料写。</Hint>
            )}
          </div>

          {formError ? <ErrorText>{formError}</ErrorText> : null}

          <div className="flex items-center gap-2">
            <Button type="submit" disabled={submitting}>
              {submitting ? "正在创建…" : "创建"}
            </Button>
            <Button variant="outlined" onClick={() => router.push("/")} disabled={submitting}>
              取消
            </Button>
          </div>
        </form>
      </Card>

      <p className="text-[12px] leading-6 text-ink-muted">
        创建后进入大纲步骤（阶段 3-2 提供）。大纲确认后才会开始写全文，写全文约 10–20 分钟。
      </p>
    </div>
  );
}
