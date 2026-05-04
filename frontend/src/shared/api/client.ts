import {
  ApplyBidPayload,
  ApplyBidResponse,
  CampaignReport,
  CampaignCommentRecord,
  CompanyConfig,
  CompanyProfile,
  CompanyProfileList,
  CompanyProfilePayload,
  CompanyProfileUpdatePayload,
  CurrentUser,
  BidChangeRecord,
  FinanceSummary,
  LoginPayload,
  MainOverview,
  RunningCampaign,
  StorageSnapshot,
  StocksSnapshot,
  StocksWorkspace,
  TrendsSnapshot,
  TokenResponse,
  UnitEconomicsProducts,
  UnitEconomicsProductsUpdateResponse,
  UnitEconomicsProductUpdateRow,
  UnitEconomicsSummary,
} from "@/shared/api/types";

export function getApiBaseUrl(): string {
  if (typeof window === "undefined") {
    return process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api";
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL || "/api";
}

function withTimeout(ms: number): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), ms);
  return {
    signal: controller.signal,
    cleanup: () => clearTimeout(timeoutId),
  };
}

async function requestJson<T>(path: string): Promise<T> {
  const apiUrl = `${getApiBaseUrl()}${path}`;
  const timeoutMs = typeof window === "undefined" ? 600000 : 25000;
  const timeout = withTimeout(timeoutMs);
  const response = await fetch(apiUrl, {
    cache: "no-store",
    signal: timeout.signal,
  }).finally(timeout.cleanup);

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText} for ${apiUrl}`);
  }

  return (await response.json()) as T;
}

export async function postJson<T>(path: string, body: unknown, token?: string): Promise<T> {
  const apiUrl = `${getApiBaseUrl()}${path}`;
  const timeoutMs = typeof window === "undefined" ? 120000 : 25000;
  const timeout = withTimeout(timeoutMs);
  const response = await fetch(apiUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: timeout.signal,
  }).finally(timeout.cleanup);

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText} for ${apiUrl}`);
  }

  return (await response.json()) as T;
}

export async function putJson<T>(path: string, body: unknown, token?: string): Promise<T> {
  const apiUrl = `${getApiBaseUrl()}${path}`;
  const timeoutMs = typeof window === "undefined" ? 120000 : 25000;
  const timeout = withTimeout(timeoutMs);
  const response = await fetch(apiUrl, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: timeout.signal,
  }).finally(timeout.cleanup);

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText} for ${apiUrl}`);
  }

  return (await response.json()) as T;
}

export async function patchJson<T>(path: string, body: unknown, token?: string): Promise<T> {
  const apiUrl = `${getApiBaseUrl()}${path}`;
  const timeoutMs = typeof window === "undefined" ? 120000 : 25000;
  const timeout = withTimeout(timeoutMs);
  const response = await fetch(apiUrl, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: timeout.signal,
  }).finally(timeout.cleanup);

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText} for ${apiUrl}`);
  }

  return (await response.json()) as T;
}

export async function getAuthedJson<T>(path: string, token: string): Promise<T> {
  const apiUrl = `${getApiBaseUrl()}${path}`;
  const timeoutMs = typeof window === "undefined" ? 120000 : 25000;
  const timeout = withTimeout(timeoutMs);
  const response = await fetch(apiUrl, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
    signal: timeout.signal,
  }).finally(timeout.cleanup);

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText} for ${apiUrl}`);
  }

  return (await response.json()) as T;
}

export function getCompanies(): Promise<CompanyConfig[]> {
  return requestJson<CompanyConfig[]>("/campaigns/companies");
}

export function getRunningCampaigns(company?: string): Promise<RunningCampaign[]> {
  const query = company ? `?company=${encodeURIComponent(company)}` : "";
  return requestJson<RunningCampaign[]>(`/campaigns/running${query}`);
}

export function getCampaignReport(params: {
  company?: string;
  dateFrom: string;
  dateTo: string;
  targetDrrPct?: number;
}): Promise<CampaignReport> {
  const search = new URLSearchParams({
    date_from: params.dateFrom,
    date_to: params.dateTo,
    target_drr_pct: String(params.targetDrrPct ?? 20),
  });
  if (params.company) {
    search.set("company", params.company);
  }
  return requestJson<CampaignReport>(`/campaigns/report?${search.toString()}`);
}

export function getMainOverview(params: {
  company?: string;
  dateFrom: string;
  dateTo: string;
  targetDrrPct?: number;
  forceRefresh?: boolean;
}): Promise<MainOverview> {
  const search = new URLSearchParams({
    date_from: params.dateFrom,
    date_to: params.dateTo,
    target_drr_pct: String(params.targetDrrPct ?? 20),
  });
  if (params.company) {
    search.set("company", params.company);
  }
  if (params.forceRefresh) {
    search.set("force_refresh", "1");
  }
  return requestJson<MainOverview>(`/campaigns/main-overview?${search.toString()}`);
}

export function login(payload: LoginPayload): Promise<TokenResponse> {
  return postJson<TokenResponse>("/auth/login", payload);
}

export function getCurrentUser(token: string): Promise<CurrentUser> {
  return getAuthedJson<CurrentUser>("/auth/me", token);
}

export function getProfileCompanies(token: string): Promise<CompanyProfileList> {
  return getAuthedJson<CompanyProfileList>("/profile/companies", token);
}

export function createProfileCompany(payload: CompanyProfilePayload, token: string): Promise<CompanyProfile> {
  return postJson<CompanyProfile>("/profile/companies", payload, token);
}

export function updateProfileCompany(
  companyId: number,
  payload: CompanyProfileUpdatePayload,
  token: string,
): Promise<CompanyProfile> {
  return patchJson<CompanyProfile>(`/profile/companies/${companyId}`, payload, token);
}

export function getRecentBidChanges(): Promise<BidChangeRecord[]> {
  return requestJson<BidChangeRecord[]>("/bids/recent");
}

export function getCampaignComments(company?: string): Promise<CampaignCommentRecord[]> {
  const query = company ? `?company=${encodeURIComponent(company)}` : "";
  return requestJson<CampaignCommentRecord[]>(`/bids/comments${query}`);
}

export function applyBid(payload: ApplyBidPayload): Promise<ApplyBidResponse> {
  return postJson<ApplyBidResponse>("/bids/apply", payload);
}

export function getStocksSnapshot(company?: string): Promise<StocksSnapshot> {
  const query = company ? `?company=${encodeURIComponent(company)}` : "";
  return requestJson<StocksSnapshot>(`/stocks/snapshot${query}`);
}

export function getStocksWorkspace(params: {
  company?: string;
  dateFrom?: string;
  dateTo?: string;
  regionalOrderMin?: number;
  regionalOrderTarget?: number;
  positionFilter?: string;
  forceRefresh?: boolean;
}): Promise<StocksWorkspace> {
  const search = new URLSearchParams();
  if (params.company) {
    search.set("company", params.company);
  }
  if (params.dateFrom) {
    search.set("date_from", params.dateFrom);
  }
  if (params.dateTo) {
    search.set("date_to", params.dateTo);
  }
  if (params.regionalOrderMin !== undefined) {
    search.set("regional_order_min", String(params.regionalOrderMin));
  }
  if (params.regionalOrderTarget !== undefined) {
    search.set("regional_order_target", String(params.regionalOrderTarget));
  }
  if (params.positionFilter) {
    search.set("position_filter", params.positionFilter);
  }
  if (params.forceRefresh) {
    search.set("force_refresh", "1");
  }
  return requestJson<StocksWorkspace>(`/stocks/workspace?${search.toString()}`);
}

export function getStorageSnapshot(company?: string, forceRefresh = false): Promise<StorageSnapshot> {
  const search = new URLSearchParams();
  if (company) {
    search.set("company", company);
  }
  if (forceRefresh) {
    search.set("force_refresh", "1");
  }
  const query = search.toString();
  return requestJson<StorageSnapshot>(`/storage/snapshot${query ? `?${query}` : ""}`);
}

export function getFinanceSummary(params: {
  company?: string;
  dateFrom: string;
  dateTo: string;
}): Promise<FinanceSummary> {
  const search = new URLSearchParams({
    date_from: params.dateFrom,
    date_to: params.dateTo,
  });
  if (params.company) {
    search.set("company", params.company);
  }
  return requestJson<FinanceSummary>(`/finance/summary?${search.toString()}`);
}

export function getTrendsSnapshot(params: {
  company?: string;
  dateFrom: string;
  dateTo: string;
  horizon?: string;
  searchFilter?: string;
}): Promise<TrendsSnapshot> {
  const search = new URLSearchParams({
    date_from: params.dateFrom,
    date_to: params.dateTo,
    horizon: params.horizon ?? "1-3 months",
  });
  if (params.company) {
    search.set("company", params.company);
  }
  if (params.searchFilter) {
    search.set("search_filter", params.searchFilter);
  }
  return requestJson<TrendsSnapshot>(`/trends/snapshot?${search.toString()}`);
}

export function getUnitEconomicsSummary(params: {
  company?: string;
  dateFrom: string;
  dateTo: string;
}): Promise<UnitEconomicsSummary> {
  const search = new URLSearchParams({
    date_from: params.dateFrom,
    date_to: params.dateTo,
  });
  if (params.company) {
    search.set("company", params.company);
  }
  return requestJson<UnitEconomicsSummary>(`/unit-economics/summary?${search.toString()}`);
}

export function getUnitEconomicsProducts(params: {
  company?: string;
  dateFrom: string;
  dateTo: string;
}): Promise<UnitEconomicsProducts> {
  const search = new URLSearchParams({
    date_from: params.dateFrom,
    date_to: params.dateTo,
  });
  if (params.company) {
    search.set("company", params.company);
  }
  return requestJson<UnitEconomicsProducts>(`/unit-economics/products?${search.toString()}`);
}

export function updateUnitEconomicsProducts(payload: {
  company?: string;
  rows: UnitEconomicsProductUpdateRow[];
}, token: string): Promise<UnitEconomicsProductsUpdateResponse> {
  return putJson<UnitEconomicsProductsUpdateResponse>("/unit-economics/products", payload, token);
}
