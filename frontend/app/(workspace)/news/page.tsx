import { PlaceholderPage } from "../_components/PlaceholderPage";
import { IconNewspaper } from "../_components/icons";

export default function NewsPage() {
  return (
    <PlaceholderPage
      group="Intelligence"
      title="News Feed"
      subtitle="Holdings-aware news stream via BYOK provider — Marketaux, Finnhub, or Alpha Vantage."
      icon={IconNewspaper}
      notes={[
        "Shares the adapter pattern with AI and market data",
        "Filters track your open positions automatically",
      ]}
    />
  );
}
