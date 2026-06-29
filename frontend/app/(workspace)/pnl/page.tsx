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
      subtitle="Realized P&L summary and the equity curve. Mode A = IBKR/TWR; Mode B = cumulative P&L ÷ cumulative net deposits."
      icon={IconTrendingUp}
    >
      {offline ? (
        <EmptyState
          tone="warn"
          title="Backend offline"
          hint="Cannot reach the API. Make sure the backend is running on :8000."
        />
      ) : !accountId || !pnl ? (
        <EmptyState
          title="No accounts yet"
          hint="Import an IBKR Flex statement on the Upload page first."
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
              sublabel="Currently open"
            />
            <Metric
              label="Base Currency"
              value={pnl.base_currency}
              sublabel="Reporting currency"
            />
          </section>

          {curve.length === 0 ? (
            <EmptyState
              title="No curve data yet"
              hint="The equity curve is derived from trades and cash flows — import a statement first."
            />
          ) : (
            <LivePnlTail key={mode} initial={curve} accountId={accountId} mode={mode} />
          )}
        </div>
      )}
    </PageShell>
  );
}
