"use client";

import { useEffect, useRef, useState } from "react";
import { getLiveSettings, subscribeLiveSettings } from "../settings";
import { isUsMarketOpen, isUsMarketSessionClosed } from "../market-hours";

export type LivePollStatus =
  | "idle"
  | "polling"
  | "live"
  | "market-closed"
  | "manual"
  | "unavailable";

export type UseLivePollingArgs<T> = {
  /** 单次 fetch —— hook 不管错误类型,抛即视为 unavailable */
  fetcher: () => Promise<T>;
  /** 成功一次 → 把数据交给消费者 */
  onData: (data: T) => void;
};

export type UseLivePollingReturn = {
  status: LivePollStatus;
  /** 上次成功的服务器响应时间(从 fetched_at 取);初始 null */
  lastFetchedAt: Date | null;
  /** 把最近一次成功的时间打到这里(消费者从响应里挑) */
  reportFetchedAt: (when: Date) => void;
};

/**
 * 通用 live 轮询 hook。
 *
 * 调度逻辑:
 *  - settings.intervalSeconds = null  → status="manual",不调度
 *  - market closed & !includeAfterHours → status="market-closed",跳过 tick
 *  - document.hidden → 跳过 tick,但保留前一个 live/closed 状态
 *  - visibilitychange 切回 → 立即触发一次额外 tick
 *  - fetcher 抛 → status="unavailable",消费者已有数据保留
 *  - fetcher 成功 → 调 onData,status="live"
 */
export function useLivePolling<T>({
  fetcher,
  onData,
}: UseLivePollingArgs<T>): UseLivePollingReturn {
  const [status, setStatus] = useState<LivePollStatus>("idle");
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [settings, setSettings] = useState(() => getLiveSettings());
  const fetcherRef = useRef(fetcher);
  const onDataRef = useRef(onData);

  // 永远拿最新的 fetcher/onData 引用,避免每次重渲染重启 interval。
  useEffect(() => {
    fetcherRef.current = fetcher;
    onDataRef.current = onData;
  });

  useEffect(() => {
    const unsub = subscribeLiveSettings(setSettings);
    return unsub;
  }, []);

  useEffect(() => {
    if (settings.intervalSeconds === null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStatus("manual");
      return;
    }

    let cancelled = false;

    const tick = async () => {
      if (cancelled) return;
      if (typeof document !== "undefined" && document.hidden) return;
      const now = new Date();
      // Fri 20:00 ET → Sun 20:00 ET there is no session at all, so we
      // never poll. Otherwise polling is gated by the after-hours toggle
      // when we're outside the regular 09:30–16:00 ET session.
      const closed = isUsMarketSessionClosed(now) ||
        (!isUsMarketOpen(now) && !settings.includeAfterHours);
      if (closed) {
        setStatus("market-closed");
        return;
      }
      setStatus("polling");
      try {
        const data = await fetcherRef.current();
        if (cancelled) return;
        onDataRef.current(data);
        setStatus("live");
      } catch {
        if (cancelled) return;
        setStatus("unavailable");
      }
    };

    tick(); // immediate first call
    const interval = window.setInterval(tick, settings.intervalSeconds * 1000);

    const onVisibility = () => {
      if (!document.hidden) tick();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [settings.intervalSeconds, settings.includeAfterHours]);

  return {
    status,
    lastFetchedAt,
    reportFetchedAt: (when: Date) => setLastFetchedAt(when),
  };
}
