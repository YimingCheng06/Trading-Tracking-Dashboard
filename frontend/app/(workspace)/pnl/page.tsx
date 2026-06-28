import {
  api,
  type Account,
  type CurveMode,
  type CurvePoint,
  type Pnl,
} from "@/lib/api";
import { fmtMoney, pnlClass } from "@/lib/format";
import { IconTrendingUp } from "../_components/icons";
import { PageShell } from "../_components/PageShell";
import { EmptyState } from "../_components/EmptyState";
import { LivePnlTail } from "./_components/LivePnlTail";

export const dynamic = "force-dynamic";

function Metric({
  label,
  value,
  sublabel,
  valueClass,
}: {
  label: string;
  value: string;
  sublabel: string;
  valueClass?: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-6">
      <p className="text-xs uppercase tracking-[0.18em] text-muted">{label}</p>
      <p
        className={`tabular mt-3 text-3xl font-semibold tracking-tight ${
          valueClass ?? ""
        }`}
      >
        {value}
      </p>
      <p className="mt-1 text-xs text-muted">{sublabel}</p>
    </div>
  );
}

export default async function PnlPage({
  searchParams,
}: {
  searchParams: Promise<{ account?: string; mode?: string }>;
}) {
  const sp = await searchParams;
  const mode: CurveMode = sp.mode === "A" ? "A" : "B";

  let accounts: Account[] = [];
  let offline = false;
  try {
    accounts = await api.accounts();
  } catch {
    offline = true;
  }
  const accountId = sp.account ?? accounts[0]?.broker_account_id;

  let pnl: Pnl | null = null;
  let curve: CurvePoint[] = [];
  if (accountId && !offline) {
    try {
      [pnl, curve] = await Promise.all([
        api.pnl(accountId),
        api.curve(accountId, mode),
      ]);
    } catch {
      offline = true;
    }
  }

  return (
    <PageShell
      group="Analysis"
      title="P&L"
      subtitle="已实现盈亏摘要与净值曲线。Mode A = IBKR/TWR;Mode B = 累计盈亏 ÷ 累计净入金。"
      icon={IconTrendingUp}
    >
      {offline ? (
        <EmptyState
          tone="warn"
          title="后端离线"
          hint="无法连接 API。确认 backend 已在 :8000 运行。"
        />
      ) : !accountId || !pnl ? (
        <EmptyState
          title="还没有账户"
          hint="先到 Upload 页导入一份 IBKR Flex 对账单。"
        />
      ) : (
        <div className="space-y-8">
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Metric
              label="Realized P&L"
              value={fmtMoney(pnl.realized_pnl)}
              sublabel={pnl.base_currency}
              valueClass={pnlClass(pnl.realized_pnl)}
            />
            <Metric
              label="Open Positions"
              value={String(pnl.open_position_count)}
              sublabel="当前持仓数"
            />
            <Metric
              label="Base Currency"
              value={pnl.base_currency}
              sublabel="规范货币"
            />
          </section>

          {curve.length === 0 ? (
            <EmptyState
              title="暂无曲线数据"
              hint="净值曲线由成交与现金流计算得出 —— 先导入对账单。"
            />
          ) : (
            <LivePnlTail initial={curve} accountId={accountId} mode={mode} />
          )}
        </div>
      )}
    </PageShell>
  );
}
