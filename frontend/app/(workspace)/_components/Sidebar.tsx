"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { AccountRail } from "./AccountRail";
import { ModuleRail } from "./ModuleRail";
import type { Account } from "@/lib/api";

/**
 * Discord 双栏壳的协调者。选中账户存在 URL `?account=` 上,
 * 缺省落到第一个账户。点击 pill 在保持当前路径的前提下改 query。
 */
export function Sidebar({ accounts }: { accounts: Account[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const fromUrl = searchParams.get("account");
  const activeId = fromUrl ?? accounts[0]?.broker_account_id ?? "";

  function selectAccount(id: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("account", id);
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="flex h-full flex-none">
      <AccountRail
        accounts={accounts}
        activeId={activeId}
        onSelect={selectAccount}
      />
      <ModuleRail activeAccountId={activeId} accounts={accounts} />
    </div>
  );
}
