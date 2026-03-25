import { ReactNode } from "react";
import { AuthGate } from "@/features/auth/components/AuthGate";

type AppShellProps = {
  children: ReactNode;
};

const navItems = [
  "Campaigns",
  "Bids",
  "Finance",
  "Stocks",
  "Storage",
  "Trends",
];

export function AppShell({ children }: AppShellProps) {
  return (
    <AuthGate>
      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand-block">
            <p className="eyebrow">Ozon Ads Platform</p>
            <h1>Control Room</h1>
            <p className="sidebar-copy">
              New product UI built in parallel while Streamlit remains the fallback runtime.
            </p>
          </div>
          <nav className="nav-list" aria-label="Primary">
            {navItems.map((item) => (
              <span className="nav-pill" key={item}>
                {item}
              </span>
            ))}
          </nav>
        </aside>
        <main className="page-content">{children}</main>
      </div>
    </AuthGate>
  );
}
