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
      subtitle="Current open positions from FIFO replay. Market value and unrealized P&L come from the latest live snapshot."
      icon={IconBriefcase}
      action={accountId ? <RefreshPricesButton accountId={accountId} /> : null}
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
      ) : positions.length === 0 ? (
        <EmptyState
          title="No open positions for this account"
          hint="Positions show up here after you import a statement."
        />
      ) : (
        <LivePositionsTable initial={positions} accountId={accountId} />
      )}
    </PageShell>
  );
}
