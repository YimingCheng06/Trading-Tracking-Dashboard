"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { api, type UploadReport } from "@/lib/api";
import { IconUpload } from "./icons";

function CountRow({
  label,
  added,
  skipped,
}: {
  label: string;
  added: number;
  skipped: number;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted">{label}</span>
      <span className="tabular">
        <span className="text-up">+{added}</span>
        <span className="ml-2 text-muted">{skipped} skipped</span>
      </span>
    </div>
  );
}

/**
 * IBKR Flex CSV 上传表单。纯本地导入(不联网);成功后展示每账户的
 * 导入计数,并引导去 Positions 刷新行情。
 */
export function UploadForm() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<UploadReport | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      setReport(await api.uploadStatement(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f) setFile(f);
        }}
        className={`flex flex-col items-center gap-3 rounded-2xl border border-dashed p-12 text-center transition-colors ${
          dragOver ? "border-accent bg-accent-soft" : "border-border bg-surface/40"
        }`}
      >
        <IconUpload width={32} height={32} className="text-accent" />
        <p className="text-sm text-muted-strong">
          拖放 IBKR Flex CSV 到这里,或
        </p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium hover:border-accent hover:text-accent"
        >
          选择文件
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        {file && <p className="tabular text-xs text-muted">{file.name}</p>}
      </div>

      <button
        type="button"
        onClick={submit}
        disabled={!file || busy}
        className="rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-rail-deep transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? "导入中…" : "导入对账单"}
      </button>

      {error && (
        <p className="rounded-xl border border-down/40 bg-down/10 px-4 py-3 text-sm text-down">
          {error}
        </p>
      )}

      {report && (
        <div className="space-y-4">
          <p className="text-sm font-medium text-up">导入完成。</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {report.accounts.map((a) => (
              <div
                key={a.broker_account_id}
                className="space-y-2 rounded-2xl border border-border bg-surface/60 p-5"
              >
                <p className="font-medium text-foreground">
                  {a.broker_account_id}
                </p>
                <CountRow label="Instruments" {...a.instruments} />
                <CountRow label="Trades" {...a.trades} />
                <CountRow label="Cash flows" {...a.cash_flows} />
                <CountRow
                  label="Corporate actions"
                  {...a.corporate_actions}
                />
              </div>
            ))}
          </div>
          {report.accounts[0] && (
            <Link
              href={`/positions?account=${encodeURIComponent(
                report.accounts[0].broker_account_id,
              )}`}
              className="inline-block text-sm font-medium text-accent hover:underline"
            >
              去 Positions 刷新行情 →
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
