"use client";

import { useEffect, useState } from "react";
import type { LivePollStatus } from "@/lib/hooks/useLivePolling";
import type { LiveSource } from "@/lib/api";

type Variant = {
  text: string;
  dotClass: string;
  textClass: string;
};

const SOURCE_LABEL: Record<LiveSource, string> = {
  ibkr: "IBKR",
  yahoo: "Yahoo (delayed)",
};

function variantFor(
  status: LivePollStatus,
  source: LiveSource | null,
  lastFetchedAt: Date | null,
  nowMs: number,
): Variant {
  switch (status) {
    case "live": {
      const ago = lastFetchedAt
        ? Math.max(0, Math.floor((nowMs - lastFetchedAt.getTime()) / 1000))
        : 0;
      const label = source ? ` · ${SOURCE_LABEL[source]}` : "";
      return {
        text: `Live${label} · ${ago}s ago`,
        dotClass: "bg-up",
        textClass: "text-muted-strong",
      };
    }
    case "polling":
      return {
        text: "Live · refreshing…",
        dotClass: "bg-up animate-pulse",
        textClass: "text-muted-strong",
      };
    case "market-closed":
      return {
        text: "Market closed",
        dotClass: "bg-muted",
        textClass: "text-muted",
      };
    case "manual":
      return {
        text: "Manual",
        dotClass: "bg-muted",
        textClass: "text-muted",
      };
    case "unavailable":
      return {
        text: "Quote unavailable",
        dotClass: "bg-down",
        textClass: "text-down",
      };
    case "idle":
    default:
      return {
        text: "Idle…",
        dotClass: "bg-muted",
        textClass: "text-muted",
      };
  }
}

/**
 * 右上角小徽章:dot + 状态文案。每秒自重渲染让 "X 秒前" 走起来(只在 live 时)。
 */
export function LiveStatusBadge({
  status,
  lastFetchedAt,
  source = null,
}: {
  status: LivePollStatus;
  lastFetchedAt: Date | null;
  source?: LiveSource | null;
}) {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (status !== "live") return;
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [status]);

  const v = variantFor(status, source, lastFetchedAt, nowMs);

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium ${v.textClass}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${v.dotClass}`} />
      {v.text}
    </span>
  );
}
