import { PlaceholderPage } from "../_components/PlaceholderPage";
import { IconPercent } from "../_components/icons";

export default function TaxPage() {
  return (
    <PlaceholderPage
      group="Analysis"
      title="Tax"
      subtitle="Short-term / long-term classification, wash-sale detection, exportable summaries."
      icon={IconPercent}
      notes={[
        "Jurisdiction selection deferred — US rules first, others pluggable",
      ]}
    />
  );
}
