import { PlaceholderPage } from "../_components/PlaceholderPage";
import { IconUpload } from "../_components/icons";

export default function UploadPage() {
  return (
    <PlaceholderPage
      group="Activity"
      title="Upload Statements"
      subtitle="Drop IBKR Daily Activity Statements (CSV / HTML) here — parsed into trades, positions, dividends, fees."
      icon={IconUpload}
      notes={[
        "Phase 1 entry point: every other screen depends on this importer",
        "Idempotent by statement ID — re-upload is safe",
      ]}
    />
  );
}
