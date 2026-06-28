import { api, type Account, type Position } from "@/lib/api";
import { IconBriefcase } from "../_components/icons";
import { PageShell } from "../_components/PageShell";
import { EmptyState } from "../_components/EmptyState";
import { RefreshPricesButton } from "../_components/RefreshPricesButton";
import { LivePositionsTable } from "./_components/LivePositionsTable";

export const dynamic = "force-dynamic";

export default async function PositionsPage({
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

  let positions: Position[] = [];
  if (accountId && !offline) {
    try {
      positions = await api.positions(accountId);
    } catch {
      offline = true;
    }
  }

  return (
    <PageShell
      group="Portfolio"
      title="Positions"
      subtitle="按 FIFO 重放得到的当前持仓;市值与未实现盈亏来自最近一次行情快照。"
      icon={IconBriefcase}
      action={accountId ? <RefreshPricesButton accountId={accountId} /> : null}
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
      ) : positions.length === 0 ? (
        <EmptyState
          title="该账户暂无持仓"
          hint="导入对账单后,持仓会在这里出现。"
        />
      ) : (
        <LivePositionsTable initial={positions} accountId={accountId} />
      )}
    </PageShell>
  );
}
