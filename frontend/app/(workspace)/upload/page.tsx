import { IconUpload } from "../_components/icons";
import { PageShell } from "../_components/PageShell";
import { UploadForm } from "../_components/UploadForm";

export default function UploadPage() {
  return (
    <PageShell
      group="Activity"
      title="Upload Statements"
      subtitle="Import IBKR Flex Query CSV — parses trades, cash flows, and corporate actions. Re-imports are idempotent by execution ID."
      icon={IconUpload}
    >
      <UploadForm />
    </PageShell>
  );
}
