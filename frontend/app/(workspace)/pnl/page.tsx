import { PlaceholderPage } from "../_components/PlaceholderPage";
import { IconTrendingUp } from "../_components/icons";

export default function PnlPage() {
  return (
    <PlaceholderPage
      group="Analysis"
      title="P&L"
      subtitle="Realized / unrealized P&L in your base currency, with FX attribution broken out."
      icon={IconTrendingUp}
      notes={[
        "Base currency picked in Settings · Preferences",
        "FIFO vs average-cost toggle lives here",
      ]}
    />
  );
}
