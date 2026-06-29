import { IconSliders } from "../../_components/icons";
import { PageShell } from "../../_components/PageShell";
import { LiveDataSettings } from "./_components/LiveDataSettings";

export default function SettingsPreferencesPage() {
  return (
    <PageShell
      group="Settings"
      title="Preferences"
      subtitle="Live refresh and display preferences for the workspace."
      icon={IconSliders}
    >
      <LiveDataSettings />
    </PageShell>
  );
}
