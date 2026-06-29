"use client";

import { useState } from "react";
import { api, type CurveMode, type CurvePoint, type CurveTail } from "@/lib/api";
import { fmtPct, pnlClass } from "@/lib/format";
import { useLivePolling } from "@/lib/hooks/useLivePolling";
import { EquityCurve } from "../../_components/EquityCurve";
import { CurveModeToggle } from "../../_components/CurveModeToggle";
import { LiveStatusBadge } from "../../_components/LiveStatusBadge";

const MODE_CAPTION: Record<CurveMode, string> = {
  A: "Mode A · TWR — past percentages stay frozen; deposits don't rescale history.",
  B: "Mode B · Net deposits — cumulative P&L ÷ current cumulative net deposits; every deposit rescales the whole curve.",
};

function applyTail(curve: CurvePoint[], tail: CurveTail): CurvePoint[] {
  const next: CurvePoint = {
    on_date: tail.on_date,
    cumulative_pnl: tail.cumulative_pnl,
    pct: tail.pct,
  };
  if (curve.length > 0 && curve[curve.length - 1].on_date === tail.on_date) {
    return [...curve.slice(0, -1), next];
  }
  return [...curve, next];
}

export function LivePnlTail({
  initial,
  accountId,
  mode,
}: {
  initial: CurvePoint[];
  accountId: string;
  mode: CurveMode;
}) {
  const [curve, setCurve] = useState<CurvePoint[]>(initial);

  const { status, lastFetchedAt, reportFetchedAt } = useLivePolling({
    fetcher: () => api.liveSnapshot(accountId, mode),
    onData: (snap) => {
      setCurve((prev) => applyTail(prev, snap.curve_tail));
      reportFetchedAt(new Date(snap.fetched_at));
    },
  });

  const last = curve[curve.length - 1];

  return (
    <section>
      <div className="mb-1 flex items-center justify-between">
        <div className="flex items-baseline gap-3">
          <h2 className="text-xs font-medium uppercase tracking-[0.22em] text-muted">
            Equity Curve
          </h2>
          {last && (
            <span
              className={`tabular text-sm font-medium ${pnlClass(last.pct)}`}
            >
              {fmtPct(last.pct)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <LiveStatusBadge status={status} lastFetchedAt={lastFetchedAt} />
          <CurveModeToggle mode={mode} />
        </div>
      </div>
      <p className="mb-3 text-xs text-muted">{MODE_CAPTION[mode]}</p>
      <EquityCurve points={curve} />
    </section>
  );
}
