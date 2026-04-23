export type CompanyConfig = {
  name: string;
  perf_client_id: string;
  perf_client_secret: string;
  seller_client_id: string;
  seller_api_key: string;
};

export type RunningCampaign = {
  campaign_id: string;
  title: string;
  state: string;
};

export type CampaignReportRow = {
  campaign_id: string;
  sku: string;
  title: string;
  money_spent: string;
  views: string;
  clicks: string;
  click_price: string;
  orders_money_ads: string;
  total_revenue: string;
  ordered_units: string;
  total_drr_pct: string;
  ctr: number;
  cr: number;
  vor: number;
  vpo: number;
};

export type CampaignReport = {
  company: string;
  date_from: string;
  date_to: string;
  target_drr_pct: number;
  running_campaigns_count: number;
  rows: CampaignReportRow[];
};

export type MainOverviewChartRow = {
  day: string;
  total_revenue: number;
  money_spent: number;
  total_drr_pct: number;
};

export type MainOverviewDailyRow = {
  day: string;
  total_revenue: number;
  total_drr_pct: number;
  money_spent: number;
  views: number;
  clicks: number;
  ordered_units: number;
  ctr: number;
  cr: number;
  organic_pct: number;
  bid_changes_cnt: number;
  comment: string;
};

export type MainOverviewWeeklyRow = {
  week: string;
  total_revenue: number;
  total_drr_pct: number;
  ebitda: number;
  ebitda_pct: number;
  total_revenue_per_day: number;
  money_spent_per_day: number;
  views_per_day: number;
  clicks_per_day: number;
  ordered_units_per_day: number;
  ctr: number;
  cr: number;
  organic_pct: number;
  bid_changes_cnt: number;
  comment: string;
};

export type MainOverview = {
  company: string;
  date_from: string;
  date_to: string;
  target_drr_pct: number;
  chart_rows: MainOverviewChartRow[];
  daily_rows: MainOverviewDailyRow[];
  weekly_rows: MainOverviewWeeklyRow[];
};

export type LoginPayload = {
  email: string;
  password: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
};

export type CurrentUser = {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  is_admin: boolean;
};

export type BidChangeRecord = {
  ts_iso: string;
  date: string;
  campaign_id: string;
  sku: string;
  old_bid_micro: number | null;
  new_bid_micro: number | null;
  reason: string;
  comment: string;
};

export type CampaignCommentRecord = {
  ts: string;
  day: string;
  week: string;
  company: string;
  campaign_id: string;
  comment: string;
};

export type ApplyBidPayload = {
  company?: string;
  campaign_id: string;
  sku: string;
  bid_rub: number;
  reason: string;
  comment?: string;
};

export type ApplyBidResponse = {
  company: string;
  campaign_id: string;
  sku: string;
  old_bid_micro: number | null;
  new_bid_micro: number;
  reason: string;
  comment: string;
};

export type StockRow = {
  sku: string;
  article: string;
  title: string;
  offer_id: string;
  cluster: string;
  turnover_grade: string;
  available_stock_count: number;
  ads_cluster: number;
  transit_stock_count: number;
};

export type StocksSnapshot = {
  company: string;
  seller_client_id: string;
  sku_count: number;
  rows: StockRow[];
};

export type StocksWorkspaceSettings = {
  regional_order_min: number;
  regional_order_target: number;
  position_filter: string;
};

export type StocksWorkspaceSummary = {
  article_count: number;
  city_count: number;
  candidate_count: number;
  approved_count: number;
};

export type StocksWorkspaceCell = {
  city: string;
  stock: number;
  need60: number;
  in_transit: number;
  total_with_transit: number;
  turnover_grade: string;
  is_candidate: boolean;
  display_value: string;
};

export type StocksWorkspaceRow = {
  article: string;
  title: string;
  cells: StocksWorkspaceCell[];
};

export type StocksWorkspace = {
  company: string;
  seller_client_id: string;
  sku_count: number;
  stocks_updated_at: string | null;
  shipments_updated_at: string | null;
  settings: StocksWorkspaceSettings;
  summary: StocksWorkspaceSummary;
  columns: string[];
  rows: StocksWorkspaceRow[];
};

export type StorageRiskRow = {
  city: string;
  article: string;
  fee_from_date: string;
  days_until_fee_start: number;
  sales_per_day: number;
  qty_remaining_now: number;
  qty_expected_at_fee_start: number;
  volume_expected_liters: number;
  estimated_daily_fee_rub: number;
};

export type StorageSnapshot = {
  company: string;
  seller_client_id: string;
  sku_count: number;
  order_count: number;
  ship_lot_count: number;
  stock_articles_count: number;
  lot_rows: Record<string, unknown>[];
  risk_rows: StorageRiskRow[];
  unknown_stock_rows: Record<string, unknown>[];
};

export type FinanceRow = {
  day: string;
  opening_balance: number;
  closing_balance: number;
  change: number;
  sales: number;
  fee: number;
  acquiring: number;
  payments: number;
  logistics: number;
  returns: number;
  storage: number;
  marketing: number;
  logistics_pct: number;
};

export type FinanceSummary = {
  company: string;
  date_from: string;
  date_to: string;
  rows: FinanceRow[];
  totals: Record<string, number>;
};

export type TrendItem = {
  id: string;
  title: string;
  trend_score: number;
  confidence_score: number;
  risk_score: number;
  summary?: string;
  reason_tags?: string;
  products_count?: number;
  revenue?: number;
};

export type TrendsSnapshot = {
  niches: TrendItem[];
  products: TrendItem[];
  external_sources: Record<string, unknown>[];
  errors: string[];
  meta: Record<string, unknown>;
};

export type UnitEconomicsDayRow = {
  day: string;
  revenue: number;
  ebitda_total: number;
  tea_cost: number;
  package_cost: number;
  label_cost: number;
  packing_cost: number;
  delivery_fbo: number;
  promotion: number;
  ozon_percent_cost: number;
  ozon_logistics: number;
  other_costs: number;
  review_points: number;
  seller_bonuses: number;
  taxes: number;
  units_sold: number;
};

export type UnitEconomicsSummary = {
  company: string;
  date_from: string;
  date_to: string;
  rows: UnitEconomicsDayRow[];
  totals: Record<string, number>;
  totals_pct: Record<string, number | string>;
};

export type UnitEconomicsProductRow = {
  sku: string;
  name: string;
  tea_cost: number;
  package_cost: number;
  label_cost: number;
  packing_cost: number;
};

export type UnitEconomicsProducts = {
  company: string;
  date_from: string;
  date_to: string;
  rows: UnitEconomicsProductRow[];
};

export type UnitEconomicsProductUpdateRow = {
  sku: string;
  position: string;
  tea_cost: number;
  package_cost: number;
  label_cost: number;
  packing_cost: number;
};

export type UnitEconomicsProductsUpdateResponse = {
  company: string;
  rows: UnitEconomicsProductRow[];
  saved_count: number;
};
