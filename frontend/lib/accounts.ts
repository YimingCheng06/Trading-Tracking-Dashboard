import type { Account } from "./api";

/** 账户 pill 的固定色板,按账户索引取色。 */
const TINTS = ["#58a6ff", "#26a69a", "#c792ea", "#f0883e", "#e3b341"];

export function accountTint(index: number): string {
  return TINTS[index % TINTS.length];
}

/** broker_account_id 末 4 位作 pill 短标(如 "U23072637" → "2637")。 */
export function accountShort(account: Account): string {
  const id = account.broker_account_id;
  return id.length > 4 ? id.slice(-4) : id;
}
