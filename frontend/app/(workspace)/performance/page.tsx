import { PlaceholderPage } from "../_components/PlaceholderPage";
import { IconSparkLine } from "../_components/icons";

export default function PerformancePage() {
  return (
    <PlaceholderPage
      group="Analysis"
      title="Performance"
      subtitle="Time-weighted / money-weighted returns, drawdown, benchmark comparison."
      icon={IconSparkLine}
      notes={[
        "Benchmarks pulled through the market-data adapter, same fallback chain as quotes",
      ]}
    />
  );
}
