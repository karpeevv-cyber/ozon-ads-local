import { BidAuditPanel } from "@/features/bids/components/BidAuditPanel";
import { BidApplyCard } from "@/features/bids/components/BidApplyCard";
import { CampaignFilters } from "@/features/campaigns/components/CampaignFilters";
import { CampaignOverview } from "@/features/campaigns/components/CampaignOverview";
import { FinancePanel } from "@/features/finance/components/FinancePanel";
import { StocksPanel } from "@/features/stocks/components/StocksPanel";
import { StoragePanel } from "@/features/storage/components/StoragePanel";
import { TrendsPanel } from "@/features/trends/components/TrendsPanel";
import { UnitEconomicsPanel } from "@/features/unit-economics/components/UnitEconomicsPanel";
import {
  getCampaignComments,
  getCampaignReport,
  getCompanies,
  getFinanceSummary,
  getRecentBidChanges,
  getRunningCampaigns,
  getStorageSnapshot,
  getStocksSnapshot,
  getTrendsSnapshot,
  getUnitEconomicsProducts,
  getUnitEconomicsSummary,
} from "@/shared/api/client";
import { AppShell } from "@/shared/ui/AppShell";
import { getDefaultDateRange } from "@/shared/utils/dates";

type HomePageProps = {
  searchParams?: Promise<{
    company?: string;
    date_from?: string;
    date_to?: string;
  }>;
};

export default async function HomePage({ searchParams }: HomePageProps) {
  const resolvedSearchParams = (await searchParams) || {};
  const companies = await getCompanies();
  const defaultRange = getDefaultDateRange();
  const selectedCompany = resolvedSearchParams.company || companies[0]?.name || "default";
  const dateFrom = resolvedSearchParams.date_from || defaultRange.dateFrom;
  const dateTo = resolvedSearchParams.date_to || defaultRange.dateTo;
  const [
    campaigns,
    report,
    recentBidChanges,
    campaignComments,
    stocksSnapshot,
    storageSnapshot,
    financeSummary,
    trendsSnapshot,
    unitEconomicsSummary,
    unitEconomicsProducts,
  ] = await Promise.all([
    getRunningCampaigns(selectedCompany),
    getCampaignReport({
      company: selectedCompany,
      dateFrom,
      dateTo,
    }),
    getRecentBidChanges(),
    getCampaignComments(selectedCompany),
    getStocksSnapshot(selectedCompany),
    getStorageSnapshot(selectedCompany),
    getFinanceSummary({
      company: selectedCompany,
      dateFrom,
      dateTo,
    }),
    getTrendsSnapshot({
      company: selectedCompany,
      dateFrom,
      dateTo,
    }),
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

  return (
    <AppShell>
      <CampaignFilters
        companies={companies}
        selectedCompany={selectedCompany}
        dateFrom={dateFrom}
        dateTo={dateTo}
      />
      <CampaignOverview companies={companies} campaigns={campaigns} report={report} />
      <section className="dashboard-grid">
        <BidApplyCard company={selectedCompany} />
        <BidAuditPanel changes={recentBidChanges} comments={campaignComments} />
        <StocksPanel snapshot={stocksSnapshot} />
        <StoragePanel snapshot={storageSnapshot} />
        <FinancePanel summary={financeSummary} />
        <TrendsPanel snapshot={trendsSnapshot} />
        <UnitEconomicsPanel summary={unitEconomicsSummary} products={unitEconomicsProducts} />
      </section>
    </AppShell>
  );
}
