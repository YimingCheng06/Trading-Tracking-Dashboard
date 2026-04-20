import { PlaceholderPage } from "../../_components/PlaceholderPage";
import { IconPlug } from "../../_components/icons";

export default function SettingsProvidersPage() {
  return (
    <PlaceholderPage
      group="Settings"
      title="Providers"
      subtitle="Market data, news, and AI provider priority — reorder fallbacks, disable sources."
      icon={IconPlug}
      notes={[
        "Default chain: IBKRRealtime → IBKRClientPortal → IBKRFlexQuery → StatementFile",
        "Quotes fall back to YahooFinance when IBKR is unavailable",
      ]}
    />
  );
}
