import { Suspense } from "react";
import { BidAuditPanel } from "@/features/bids/components/BidAuditPanel";
import { BidApplyCard } from "@/features/bids/components/BidApplyCard";
import { AllCampaignsPanel } from "@/features/campaigns/components/AllCampaignsPanel";
import { CampaignFilters } from "@/features/campaigns/components/CampaignFilters";
import { CurrentCampaignsPanel } from "@/features/campaigns/components/CurrentCampaignsPanel";
import { FinancePanel } from "@/features/finance/components/FinancePanel";
import { MainDashboard } from "@/features/main/components/MainDashboard";
import { ProfilePanel } from "@/features/profile/components/ProfilePanel";
import { StocksPanel } from "@/features/stocks/components/StocksPanel";
import { StoragePanel } from "@/features/storage/components/StoragePanel";
import { TrendsPanel } from "@/features/trends/components/TrendsPanel";
import { UnitEconomicsEditor } from "@/features/unit-economics/components/UnitEconomicsEditor";
import { UnitEconomicsPanel } from "@/features/unit-economics/components/UnitEconomicsPanel";
import {
  getCampaignComments,
  getCampaignReport,
  getCompanies,
  getCurrentCampaignDetail,
  getFinanceSummary,
  getMainOverview,
  getRecentBidChanges,
  getStorageSnapshot,
  getStocksWorkspace,
  getTrendsSnapshot,
  getUnitEconomicsProducts,
  getUnitEconomicsSummary,
} from "@/shared/api/client";
import { CompanyConfig, CurrentCampaignDetail } from "@/shared/api/types";
import { AppShell } from "@/shared/ui/AppShell";
import { getDefaultDateRange } from "@/shared/utils/dates";

type HomePageProps = {
  searchParams?: Promise<{
    company?: string;
    date_from?: string;
    date_to?: string;
    tab?: string;
    stocks_regional_order_min?: string;
    stocks_regional_order_target?: string;
    stocks_position_filter?: string;
    stocks_highlight_levels?: string;
    stocks_review_mode?: string;
    stocks_refresh?: string;
    storage_refresh?: string;
    main_refresh?: string;
    current_campaign_id?: string;
  }>;
};

type SupportedTab =
  | "main"
  | "all-campaigns"
  | "current-campaigns"
  | "tests"
  | "unit-economics"
  | "unit-economics-products"
  | "finance-balance"
  | "stocks"
  | "storage"
  | "search-trends"
  | "formulas"
  | "profile";

const supportedTabs = new Set<SupportedTab>([
  "main",
  "all-campaigns",
  "current-campaigns",
  "tests",
  "unit-economics",
  "unit-economics-products",
  "finance-balance",
  "stocks",
  "storage",
  "search-trends",
  "formulas",
  "profile",
]);

function resolveTab(value?: string): SupportedTab {
  return supportedTabs.has(value as SupportedTab) ? (value as SupportedTab) : "main";
}

function PlaceholderPanel({
  title,
  eyebrow,
  copy,
}: {
  title: string;
  eyebrow: string;
  copy: string;
}) {
  return (
    <article className="panel-card panel-card-wide section-card">
      <div className="panel-header">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h3>{title}</h3>
        </div>
        <span className="status-badge">pending</span>
      </div>
      <p className="muted-copy">{copy}</p>
    </article>
  );
}

function LoadErrorPanel({ title, details }: { title: string; details: string }) {
  return (
    <article className="panel-card panel-card-wide section-card">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Data error</p>
          <h3>{title}</h3>
        </div>
        <span className="status-badge">retry</span>
      </div>
      <p className="muted-copy">{details}</p>
    </article>
  );
}

function isAbortLikeError(error: unknown): boolean {
  if (!error || typeof error !== "object") {
    return false;
  }
  const maybeError = error as { name?: string; message?: string };
  const name = String(maybeError.name || "").toLowerCase();
  const message = String(maybeError.message || "").toLowerCase();
  return name.includes("abort") || message.includes("aborted");
}

function emptyCurrentCampaignDetail(params: {
  company: string;
  dateFrom: string;
  dateTo: string;
}): CurrentCampaignDetail {
  return {
    company: params.company,
    date_from: params.dateFrom,
    date_to: params.dateTo,
    campaigns: [],
    selected_campaign_id: "",
    selected_campaign_title: "",
    sku: "",
    article: "",
    current_bid_rub: null,
    is_single_sku: false,
    totals: null,
    parameters: {},
    weekly_rows: [],
    daily_rows: [],
    comments: [],
    test_history: [],
  };
}

function UnitEconomicsProductsPanel({
  products,
}: {
  products: Awaited<ReturnType<typeof getUnitEconomicsProducts>>;
}) {
  return (
    <>
      <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Unit economics products</p>
            <h3>Editable SKU cost matrix</h3>
          </div>
          <span className="status-badge">{products.rows.length} sku</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Name</th>
                <th>Tea</th>
                <th>Package</th>
                <th>Label</th>
                <th>Packing</th>
              </tr>
            </thead>
            <tbody>
              {products.rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="empty-cell">
                    No unit economics products loaded yet.
                  </td>
                </tr>
              ) : (
                products.rows.map((row) => (
                  <tr key={row.sku}>
                    <td>{row.sku}</td>
                    <td>{row.name || row.sku}</td>
                    <td>{row.tea_cost}</td>
                    <td>{row.package_cost}</td>
                    <td>{row.label_cost}</td>
                    <td>{row.packing_cost}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </article>
      <UnitEconomicsEditor company={products.company} rows={products.rows} />
    </>
  );
}

async function renderTabContent(params: {
  activeTab: SupportedTab;
  selectedCompany: string;
  dateFrom: string;
  dateTo: string;
  companies: CompanyConfig[];
  stocksRegionalOrderMin: number;
  stocksRegionalOrderTarget: number;
  stocksPositionFilter: string;
  stocksHighlightLevels: string[];
  stocksReviewMode: boolean;
  mainRefresh: boolean;
  stocksRefresh: boolean;
  storageRefresh: boolean;
  currentCampaignId?: string;
}) {
  const {
    activeTab,
    selectedCompany,
    dateFrom,
    dateTo,
    companies,
    stocksRegionalOrderMin,
    stocksRegionalOrderTarget,
    stocksPositionFilter,
    stocksHighlightLevels,
    stocksReviewMode,
    mainRefresh,
    stocksRefresh,
    storageRefresh,
    currentCampaignId,
  } = params;

  switch (activeTab) {
    case "main": {
      const overview = await getMainOverview({
        company: selectedCompany,
        dateFrom,
        dateTo,
        forceRefresh: mainRefresh,
      });
      return <MainDashboard overview={overview} />;
    }
    case "all-campaigns": {
      const reportPromise = getCampaignReport({
        company: selectedCompany,
        dateFrom,
        dateTo,
      });
      const detailPromise = currentCampaignId
        ? getCurrentCampaignDetail({
            company: selectedCompany,
            dateFrom,
            dateTo,
            campaignId: currentCampaignId,
          })
        : Promise.resolve(emptyCurrentCampaignDetail({ company: selectedCompany, dateFrom, dateTo }));
      const [report, detail] = await Promise.all([reportPromise, detailPromise]);
      return <AllCampaignsPanel report={report} currentDetail={detail} />;
    }
    case "current-campaigns": {
      const detail = await getCurrentCampaignDetail({
        company: selectedCompany,
        dateFrom,
        dateTo,
        campaignId: currentCampaignId,
      });
      return <CurrentCampaignsPanel detail={detail} />;
    }
    case "tests": {
      const [recentBidChanges, campaignComments] = await Promise.all([
        getRecentBidChanges(),
        getCampaignComments(selectedCompany),
      ]);
      return (
        <section className="dashboard-grid section-grid">
          <BidApplyCard company={selectedCompany} />
          <BidAuditPanel changes={recentBidChanges} comments={campaignComments} />
        </section>
      );
    }
    case "unit-economics": {
      const [summary, products] = await Promise.all([
        getUnitEconomicsSummary({
          company: selectedCompany,
          dateFrom,
          dateTo,
        }),
        getUnitEconomicsProducts({
          company: selectedCompany,
          dateFrom,
          dateTo,
        }),
      ]);
      return <UnitEconomicsPanel summary={summary} products={products} />;
    }
    case "unit-economics-products": {
      const products = await getUnitEconomicsProducts({
        company: selectedCompany,
        dateFrom,
        dateTo,
      });
      return <UnitEconomicsProductsPanel products={products} />;
    }
    case "finance-balance": {
      const summary = await getFinanceSummary({
        company: selectedCompany,
        dateFrom,
        dateTo,
      });
      return <FinancePanel summary={summary} />;
    }
    case "stocks": {
      const workspace = await getStocksWorkspace({
        company: selectedCompany,
        dateFrom,
        dateTo,
        regionalOrderMin: stocksRegionalOrderMin,
        regionalOrderTarget: stocksRegionalOrderTarget,
        positionFilter: stocksPositionFilter,
        forceRefresh: stocksRefresh,
      });
      return (
        <StocksPanel
          workspace={workspace}
          highlightLevels={stocksHighlightLevels}
          reviewMode={stocksReviewMode}
        />
      );
    }
    case "storage": {
      const snapshot = await getStorageSnapshot(selectedCompany, storageRefresh);
      return <StoragePanel snapshot={snapshot} />;
    }
    case "search-trends": {
      const snapshot = await getTrendsSnapshot({
        company: selectedCompany,
        dateFrom,
        dateTo,
      });
      return <TrendsPanel snapshot={snapshot} />;
    }
    case "formulas":
      return (
        <PlaceholderPanel
          eyebrow="Formulas"
          title="Formula workspace"
          copy="This section is reserved for formula logic and decision calculators. The navigation is ready; the feature module still needs to be extracted into the new stack."
        />
      );
    case "profile":
      return <ProfilePanel />;
    default:
      return null;
  }
}

function TabContentSkeleton() {
  return (
    <section className="dashboard-grid section-grid">
      <article className="panel-card panel-card-wide section-card skeleton-card">
        <div className="skeleton-line skeleton-line-lg" />
        <div className="skeleton-line" />
        <div className="skeleton-line" />
      </article>
      <article className="panel-card panel-card-wide section-card skeleton-card">
        <div className="skeleton-line skeleton-line-lg" />
        <div className="skeleton-grid">
          {Array.from({ length: 8 }).map((_, idx) => (
            <span className="skeleton-cell" key={idx} />
          ))}
        </div>
      </article>
    </section>
  );
}

async function TabContent(params: {
  activeTab: SupportedTab;
  selectedCompany: string;
  dateFrom: string;
  dateTo: string;
  companies: CompanyConfig[];
  stocksRegionalOrderMin: number;
  stocksRegionalOrderTarget: number;
  stocksPositionFilter: string;
  stocksHighlightLevels: string[];
  stocksReviewMode: boolean;
  mainRefresh: boolean;
  stocksRefresh: boolean;
  storageRefresh: boolean;
  currentCampaignId?: string;
}) {
  try {
    return await renderTabContent(params);
  } catch (error) {
    if (isAbortLikeError(error)) {
      if (params.activeTab === "stocks" && params.stocksRefresh) {
        return await renderTabContent({ ...params, stocksRefresh: false });
      }
      if (params.activeTab === "storage" && params.storageRefresh) {
        return await renderTabContent({ ...params, storageRefresh: false });
      }
      return <TabContentSkeleton />;
    }
    const message =
      error instanceof Error
        ? error.message
        : "Не удалось загрузить данные вкладки. Повторите попытку через пару секунд.";
    console.error("Tab render failed", {
      tab: params.activeTab,
      company: params.selectedCompany,
      dateFrom: params.dateFrom,
      dateTo: params.dateTo,
      message,
    });
    return <LoadErrorPanel title={`Ошибка загрузки вкладки "${params.activeTab}"`} details={message} />;
  }
}

export default async function HomePage({ searchParams }: HomePageProps) {
  const resolvedSearchParams = (await searchParams) || {};
  let companies: CompanyConfig[] = [];
  try {
    companies = await getCompanies();
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown companies load error";
    console.error("Companies load failed", { message });
  }
  const defaultRange = getDefaultDateRange();
  const selectedCompany = resolvedSearchParams.company || companies[0]?.name || "default";
  const dateFrom = resolvedSearchParams.date_from || defaultRange.dateFrom;
  const dateTo = resolvedSearchParams.date_to || defaultRange.dateTo;
  const activeTab = resolveTab(resolvedSearchParams.tab);
  const stocksRegionalOrderMin = Math.max(0, Number.parseInt(resolvedSearchParams.stocks_regional_order_min || "2", 10) || 2);
  const stocksRegionalOrderTarget = Math.max(
    stocksRegionalOrderMin,
    Number.parseInt(resolvedSearchParams.stocks_regional_order_target || "5", 10) || 5,
  );
  const stocksPositionFilter = ["ALL", "CORE", "ADDITIONAL"].includes(
    String(resolvedSearchParams.stocks_position_filter || "").toUpperCase(),
  )
    ? String(resolvedSearchParams.stocks_position_filter || "ALL").toUpperCase()
    : "ALL";
  const allowedHighlightLevels = new Set(["paid_now", "paid_30", "paid_60"]);
  const stocksHighlightLevels = String(resolvedSearchParams.stocks_highlight_levels || "paid_now")
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter((value, index, arr) => allowedHighlightLevels.has(value) && arr.indexOf(value) === index);
  const stocksReviewMode = String(resolvedSearchParams.stocks_review_mode || "1") !== "0";
  const storageRefresh = Boolean(resolvedSearchParams.storage_refresh);
  const tabStateKey = `${activeTab}:${selectedCompany}:${dateFrom}:${dateTo}:${stocksRegionalOrderMin}:${stocksRegionalOrderTarget}:${stocksPositionFilter}:${stocksHighlightLevels.join("|")}:${stocksReviewMode ? "1" : "0"}:${resolvedSearchParams.main_refresh || ""}:${resolvedSearchParams.stocks_refresh || ""}:${resolvedSearchParams.storage_refresh || ""}:${resolvedSearchParams.current_campaign_id || ""}`;
  return (
    <AppShell
      filters={
        <CampaignFilters
          companies={companies}
          selectedCompany={selectedCompany}
          dateFrom={dateFrom}
          dateTo={dateTo}
        />
      }
    >
      <Suspense key={tabStateKey} fallback={<TabContentSkeleton />}>
        <TabContent
          activeTab={activeTab}
          selectedCompany={selectedCompany}
          dateFrom={dateFrom}
          dateTo={dateTo}
          companies={companies}
          stocksRegionalOrderMin={stocksRegionalOrderMin}
          stocksRegionalOrderTarget={stocksRegionalOrderTarget}
          stocksPositionFilter={stocksPositionFilter}
          stocksHighlightLevels={stocksHighlightLevels}
          stocksReviewMode={stocksReviewMode}
          mainRefresh={Boolean(resolvedSearchParams.main_refresh)}
          stocksRefresh={Boolean(resolvedSearchParams.stocks_refresh)}
          storageRefresh={storageRefresh}
          currentCampaignId={resolvedSearchParams.current_campaign_id}
        />
      </Suspense>
    </AppShell>
  );
}
