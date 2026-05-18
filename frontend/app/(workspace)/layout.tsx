import { Suspense } from "react";
import { Sidebar } from "./_components/Sidebar";
import { api, type Account } from "@/lib/api";

export const dynamic = "force-dynamic";

async function getAccounts(): Promise<Account[]> {
  try {
    return await api.accounts();
  } catch {
    return [];
  }
}

/**
 * Workspace 壳:左侧 Discord 双栏 + 右侧页面。账户列表服务端拉取,
 * 失败降级为空数组(账户栏只剩 Logo + Add)。
 */
export default async function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const accounts = await getAccounts();

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      <Suspense
        fallback={
          <div
            style={{
              width: "calc(var(--rail-width) + var(--module-width))",
            }}
          />
        }
      >
        <Sidebar accounts={accounts} />
      </Suspense>
      <main className="ambient-glow relative flex-1 overflow-y-auto">
        <div className="relative z-10">{children}</div>
      </main>
    </div>
  );
}
