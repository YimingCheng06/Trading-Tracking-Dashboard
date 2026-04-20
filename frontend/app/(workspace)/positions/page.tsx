import { PlaceholderPage } from "../_components/PlaceholderPage";
import { IconBriefcase } from "../_components/icons";

export default function PositionsPage() {
  return (
    <PlaceholderPage
      group="Portfolio"
      title="Positions"
      subtitle="Open positions across stocks, ETFs, and options — underlying, strike, expiry, greeks once the IBKR adapter lands."
      icon={IconBriefcase}
      notes={[
        "Source priority: IBKRRealtime → IBKRClientPortal → IBKRFlexQuery → StatementFile",
        "FX column reflects base-currency conversion per locked P&L design",
      ]}
    />
  );
}
