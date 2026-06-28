import { IconSliders } from "../../_components/icons";
import { PageShell } from "../../_components/PageShell";
import { LiveDataSettings } from "./_components/LiveDataSettings";

export default function SettingsPreferencesPage() {
  return (
    <PageShell
      group="Settings"
      title="Preferences"
      subtitle="实时刷新、显示偏好等用户级设置。"
      icon={IconSliders}
    >
      <LiveDataSettings />
    </PageShell>
  );
}
