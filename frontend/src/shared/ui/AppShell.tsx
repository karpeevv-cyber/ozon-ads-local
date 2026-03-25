import Link from "next/link";
import { ReactNode } from "react";
import { AuthGate } from "@/features/auth/components/AuthGate";

type AppShellProps = {
  activeTab: string;
  company?: string;
  dateFrom?: string;
  dateTo?: string;
  children: ReactNode;
};

const navItems = [
  { id: "main", label: "Main" },
  { id: "all-campaigns", label: "All campaigns" },
  { id: "current-campaigns", label: "Current campaigns" },
  { id: "tests", label: "Tests" },
  { id: "unit-economics", label: "Unit Economics" },
  { id: "unit-economics-products", label: "Unit Economics Products" },
  { id: "finance-balance", label: "Finance balance" },
  { id: "stocks", label: "Stocks" },
  { id: "storage", label: "Storage" },
  { id: "search-trends", label: "Search Trends" },
  { id: "formulas", label: "Formulas" },
];

export function AppShell({ activeTab, company, dateFrom, dateTo, children }: AppShellProps) {
  const makeHref = (tab: string) => {
    const params = new URLSearchParams();
    params.set("tab", tab);
    if (company) {
      params.set("company", company);
    }
    if (dateFrom) {
      params.set("date_from", dateFrom);
    }
    if (dateTo) {
      params.set("date_to", dateTo);
    }
    return `/?${params.toString()}`;
  };

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
              <Link
                className={`nav-pill${item.id === activeTab ? " nav-pill-active" : ""}`}
                href={makeHref(item.id)}
                key={item.id}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </aside>
        <main className="page-content">{children}</main>
      </div>
    </AuthGate>
  );
}
