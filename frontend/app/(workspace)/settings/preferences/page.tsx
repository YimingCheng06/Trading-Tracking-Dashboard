import { PlaceholderPage } from "../../_components/PlaceholderPage";
import { IconSliders } from "../../_components/icons";

export default function SettingsPreferencesPage() {
  return (
    <PlaceholderPage
      group="Settings"
      title="Preferences"
      subtitle="Base currency, cost-basis method, display density, theme accents."
      icon={IconSliders}
      notes={[
        "Base currency picker drives every P&L conversion",
        "FIFO vs average-cost decision is account-scoped",
      ]}
    />
  );
}
