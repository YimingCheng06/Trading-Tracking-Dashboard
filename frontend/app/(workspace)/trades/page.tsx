import { api, type Account, type Trade } from "@/lib/api";
import { fmtMoney, fmtNum, fmtDate, pnlClass } from "@/lib/format";
import { IconArrowSwap } from "../_components/icons";
import { PageShell } from "../_components/PageShell";
import { DataTable, type Column } from "../_components/DataTable";
import { EmptyState } from "../_components/EmptyState";

export const dynamic = "force-dynamic";

const COLUMNS: Column[] = [
  { key: "date", label: "Date" },
  { key: "symbol", label: "Symbol" },
  { key: "side", label: "Side" },
  { key: "qty", label: "Qty", numeric: true },
  { key: "price", label: "Price", numeric: true },
  { key: "proceeds", label: "Proceeds", numeric: true },
  { key: "commission", label: "Commission", numeric: true },
  { key: "rpnl", label: "Realized P&L", numeric: true },
];

function SideBadge({ side }: { side: string }) {
  const buy = side.toUpperCase() === "BUY";
  return (
    <span
      className={`rounded-md px-2 py-0.5 text-xs font-medium ${
        buy ? "bg-up/15 text-up" : "bg-down/15 text-down"
      }`}
    >
      {side.toUpperCase()}
    </span>
  );
}

export default async function TradesPage({
  searchParams,
}: {
  searchParams: Promise<{ account?: string }>;
}) {
  const { account } = await searchParams;

  let accounts: Account[] = [];
  let offline = false;
  try {
    accounts = await api.accounts();
  } catch {
    offline = true;
  }
  const accountId = account ?? accounts[0]?.broker_account_id;

  let trades: Trade[] = [];
  if (accountId && !offline) {
    try {
      trades = await api.trades(accountId);
    } catch {
      offline = true;
    }
  }

  return (
    <PageShell
      group="Activity"
      title="Trades"
      subtitle="Trade executions parsed from imported statements, most recent first."
      icon={IconArrowSwap}
    >
      {offline ? (
        <EmptyState
          tone="warn"
          title="Backend offline"
          hint="Cannot reach the API. Make sure the backend is running on :8000."
        />
      ) : !accountId ? (
        <EmptyState
          title="No accounts yet"
          hint="Import an IBKR Flex statement on the Upload page first."
        />
      ) : trades.length === 0 ? (
        <EmptyState
          title="No trades for this account"
          hint="Trades show up here after you import a statement."
        />
      ) : (
        <DataTable
          columns={COLUMNS}
          rows={trades.map((t) => ({
            id: t.trade_id,
            cells: [
              fmtDate(t.executed_at),
              <span key="s" className="font-medium text-foreground">
                {t.symbol}
              </span>,
              <SideBadge key="side" side={t.side} />,
              fmtNum(t.quantity),
              fmtMoney(t.price),
              fmtMoney(t.proceeds_usd),
              fmtMoney(t.commission_usd),
              <span key="r" className={pnlClass(t.realized_pnl_ibkr)}>
                {fmtMoney(t.realized_pnl_ibkr)}
              </span>,
            ],
          }))}
        />
      )}
    </PageShell>
  );
}
