import { IconUpload } from "../_components/icons";
import { PageShell } from "../_components/PageShell";
import { UploadForm } from "../_components/UploadForm";

export default function UploadPage() {
  return (
    <PageShell
      group="Activity"
      title="Upload Statements"
      subtitle="导入 IBKR Flex Query CSV —— 解析成交、现金流、公司行动。重复导入按 ID 幂等。"
      icon={IconUpload}
    >
      <UploadForm />
    </PageShell>
  );
}
