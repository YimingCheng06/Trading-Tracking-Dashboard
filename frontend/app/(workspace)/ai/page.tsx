import { PlaceholderPage } from "../_components/PlaceholderPage";
import { IconBrain } from "../_components/icons";

export default function AiPage() {
  return (
    <PlaceholderPage
      group="Intelligence"
      title="AI Chat"
      subtitle="Bring your own Claude / OpenAI / Ollama key. The dashboard exposes portfolio tools; the model drives the analysis."
      icon={IconBrain}
      notes={[
        "Tools: get_portfolio_snapshot · get_pnl · get_trade_history · get_position_detail · get_news_for_holdings · get_market_context",
        "Keys stored encrypted client-side only — never sent to the backend",
      ]}
    />
  );
}
