import { PlaceholderPage } from "../../_components/PlaceholderPage";
import { IconKey } from "../../_components/icons";

export default function SettingsKeysPage() {
  return (
    <PlaceholderPage
      group="Settings"
      title="API Keys"
      subtitle="BYOK storage for model providers and news APIs. Keys encrypted in the browser with your passphrase."
      icon={IconKey}
      notes={[
        "No server-side storage — clearing browser data clears keys",
        "Export / import flow lands alongside the intelligence layer",
      ]}
    />
  );
}
