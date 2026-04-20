import { PlaceholderPage } from "../_components/PlaceholderPage";
import { IconArrowSwap } from "../_components/icons";

export default function TradesPage() {
  return (
    <PlaceholderPage
      group="Activity"
      title="Trades"
      subtitle="Executed trade history with FIFO / average cost lot tracking and realized P&L per close."
      icon={IconArrowSwap}
      notes={[
        "Lot-matching engine will land alongside the statement importer",
        "Options exercises / assignments treated as linked trade pairs",
      ]}
    />
  );
}
