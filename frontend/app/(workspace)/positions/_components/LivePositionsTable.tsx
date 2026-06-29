"use client";

import { useState } from "react";
import { api, type Position } from "@/lib/api";
import { fmtMoney, fmtNum, pnlClass } from "@/lib/format";
import { useLivePolling } from "@/lib/hooks/useLivePolling";
import {
  DataTable,
  type Column,
} from "../../_components/DataTable";
import { LiveStatusBadge } from "../../_components/LiveStatusBadge";

const COLUMNS: Column[] = [
  { key: "symbol", label: "Symbol" },
  { key: "qty", label: "Qty", numeric: true },
  { key: "avg", label: "Avg Cost", numeric: true },
  { key: "cost", label: "Cost Basis", numeric: true },
  { key: "price", label: "Mkt Price", numeric: true },
  { key: "value", label: "Mkt Value", numeric: true },
  { key: "upnl", label: "Unrealized P&L", numeric: true },
];

export function LivePositionsTable({
  initial,
  accountId,
}: {
  initial: Position[];
  accountId: string;
}) {
  const [positions, setPositions] = useState<Position[]>(initial);

  const { status, lastFetchedAt, reportFetchedAt } = useLivePolling({
    fetcher: () => api.liveSnapshot(accountId, "B"),
    onData: (snap) => {
      setPositions(snap.positions);
      reportFetchedAt(new Date(snap.fetched_at));
    },
  });

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <LiveStatusBadge status={status} lastFetchedAt={lastFetchedAt} />
      </div>
      <DataTable
        columns={COLUMNS}
        rows={positions.map((p) => ({
          id: p.symbol,
          cells: [
            <span key="s" className="font-medium text-foreground">
              {p.symbol}
            </span>,
            fmtNum(p.quantity),
            fmtMoney(p.average_cost),
            fmtMoney(p.cost_basis),
            fmtMoney(p.market_price),
            fmtMoney(p.market_value),
            <span key="u" className={pnlClass(p.unrealized_pnl)}>
              {fmtMoney(p.unrealized_pnl)}
            </span>,
          ],
        }))}
      />
    </div>
  );
}
