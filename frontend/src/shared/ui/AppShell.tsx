"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { AuthGate } from "@/features/auth/components/AuthGate";

type AppShellProps = {
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

export function AppShell({ children }: AppShellProps) {
  const searchParams = useSearchParams();
  const [optimisticTab, setOptimisticTab] = useState<string | null>(null);
  const activeTab = searchParams.get("tab") || "main";
  const displayedTab = optimisticTab ?? activeTab;
  const company = searchParams.get("company");
  const dateFrom = searchParams.get("date_from");
  const dateTo = searchParams.get("date_to");
  const showTabSwitchSkeleton = optimisticTab !== null && optimisticTab !== activeTab;

  useEffect(() => {
    if (optimisticTab && optimisticTab === activeTab) {
      setOptimisticTab(null);
    }
  }, [activeTab, optimisticTab]);

  useEffect(() => {
    if (!optimisticTab) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      setOptimisticTab(null);
    }, 6000);
    return () => window.clearTimeout(timeoutId);
  }, [optimisticTab]);

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
                className={`nav-pill${item.id === displayedTab ? " nav-pill-active" : ""}`}
                href={makeHref(item.id)}
                key={item.id}
                onClick={() => setOptimisticTab(item.id)}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </aside>
        <main className="page-content page-content-shell">
          {children}
          {showTabSwitchSkeleton ? (
            <div className="tab-loading-overlay" aria-live="polite" aria-busy="true">
              <div className="panel-card panel-card-wide section-card skeleton-card">
                <div className="skeleton-line skeleton-line-lg" />
                <div className="skeleton-line" />
                <div className="skeleton-line" />
              </div>
              <div className="panel-card panel-card-wide section-card skeleton-card">
                <div className="skeleton-line skeleton-line-lg" />
                <div className="skeleton-grid">
                  {Array.from({ length: 8 }).map((_, idx) => (
                    <span className="skeleton-cell" key={idx} />
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </main>
      </div>
    </AuthGate>
  );
}
