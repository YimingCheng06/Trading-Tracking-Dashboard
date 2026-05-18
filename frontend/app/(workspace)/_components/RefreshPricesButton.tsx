"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { IconRefresh } from "./icons";

/**
 * 刷新行情按钮 —— 唯一触发后端联网(Yahoo)重建快照的入口。
 * 成功后 router.refresh() 让服务端组件用新快照重渲染。
 */
export function RefreshPricesButton({ accountId }: { accountId: string }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loading = busy || isPending;

  async function onClick() {
    setError(null);
    setBusy(true);
    try {
      await api.refreshPrices(accountId);
      startTransition(() => router.refresh());
    } catch (e) {
      setError(e instanceof Error ? e.message : "刷新失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={onClick}
        disabled={loading || !accountId}
        className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        <IconRefresh
          width={16}
          height={16}
          className={loading ? "animate-spin" : ""}
        />
        {loading ? "刷新中…" : "刷新行情"}
      </button>
      {error && <p className="max-w-xs text-right text-xs text-down">{error}</p>}
    </div>
  );
}
