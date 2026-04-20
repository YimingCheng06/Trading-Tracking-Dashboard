import { Sidebar } from "./_components/Sidebar";

/**
 * Workspace shell. Renders the Discord-style twin rail on the left and
 * fills the remainder with the active page. `h-dvh` + inner overflow lets
 * the main area scroll while the sidebar stays pinned.
 */
export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      <Sidebar />
      <main className="ambient-glow relative flex-1 overflow-y-auto">
        <div className="relative z-10">{children}</div>
      </main>
    </div>
  );
}
