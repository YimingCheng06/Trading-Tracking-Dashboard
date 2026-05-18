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
      subtitle="导入对账单解析出的成交流水,按成交时间倒序。"
      icon={IconArrowSwap}
    >
      {offline ? (
        <EmptyState
          tone="warn"
          title="后端离线"
          hint="无法连接 API。确认 backend 已在 :8000 运行。"
        />
      ) : !accountId ? (
        <EmptyState
          title="还没有账户"
          hint="先到 Upload 页导入一份 IBKR Flex 对账单。"
        />
      ) : trades.length === 0 ? (
        <EmptyState
          title="该账户暂无成交"
          hint="导入对账单后,成交会在这里出现。"
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
