import { PlaceholderPage } from "../_components/PlaceholderPage";
import { IconWallet } from "../_components/icons";

export default function HoldingsPage() {
  return (
    <PlaceholderPage
      group="Portfolio"
      title="Holdings"
      subtitle="Aggregate holdings view grouped by asset class, sector, and currency exposure."
      icon={IconWallet}
      notes={[
        "Cross-account aggregation once multiple accounts are wired",
        "Tap a row to jump into the position detail page",
      ]}
    />
  );
}
