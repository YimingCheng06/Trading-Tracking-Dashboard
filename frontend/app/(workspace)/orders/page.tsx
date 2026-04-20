import { PlaceholderPage } from "../_components/PlaceholderPage";
import { IconReceipt } from "../_components/icons";

export default function OrdersPage() {
  return (
    <PlaceholderPage
      group="Activity"
      title="Orders"
      subtitle="Working / filled / cancelled orders with status transitions when the live IBKR feed comes online."
      icon={IconReceipt}
      notes={[
        "Read-only in early phases — no order placement from this dashboard",
      ]}
    />
  );
}
