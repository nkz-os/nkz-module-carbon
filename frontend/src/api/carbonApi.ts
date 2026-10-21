// Resolve API base URL safely for both browser (import.meta.env) and
// Node.js CJS manifest-emit context (process.env).
const API_BASE = (typeof process !== 'undefined' && process.env?.VITE_API_URL)
  || (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL)
  ? `${
      (typeof process !== 'undefined' && process.env?.VITE_API_URL)
      || (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL)
    }/api/carbon`
  : '/api/carbon';

export type CarbonPools = Record<'DPM' | 'RPM' | 'BIO' | 'HUM' | 'IOM', number>;

export interface MissingItem {
  item: string;
  reason: string;
  effect: string;
}

export interface CycleResult {
  crop_id: string;
  species: string;
  role: string;
  start: string;
  end: string | null;
  start_provenance: string;
  end_provenance: string | null;
  campaign_label: number | null;
  days_in_period: number;
  days_computed: number;
  npp_tC_ha: number;
  c_to_soil_tC_ha: number | null;
  exported_c_tC_ha: number | null;
}

export interface MonthResult {
  month: number;
  temp_c: number;
  rain_mm: number;
  et0_mm: number;
  covered: boolean;
  cover_days: number;
  plant_c_tC_ha: number;
  fym_c_tC_ha: number;
  co2_c_tC_ha: number | null;
}

/** One stored campaign balance. Carbon in tC/ha, CO2 in tCO2/ha; absent = not computed. */
export interface CampaignRow {
  parcel_id: string;
  campaign_label: number;
  period_start: string;
  period_end: string;
  computed_through?: string;
  data_tier: number;
  cover_days: number;
  bare_days: number;
  tier1_coverage: number;
  gpp_total?: number;
  npp_total?: number;
  co2_sequestered_gross?: number;
  heterotrophic_respiration?: number;
  soc_start?: number;
  soc_end?: number;
  soil_carbon_delta?: number;
  soil_carbon_delta_ci95?: number;
  nee?: number;
  necb?: number;
  n2o_emissions?: number;
  co2eq_net?: number;
  gpp_ci95_pct?: number;
  cycle_breakdown: CycleResult[];
  monthly_balance: MonthResult[];
  missing: MissingItem[];
  assumptions: string[];
  initial_state_source: string;
  data_sources: string[];
  calculated_at: string;
  engine_version: string;
  soil_clay_pct?: number;
  soil_depth_cm?: number;
  soil_source?: string;
  pools_end?: CarbonPools | null;
  pools_state_date?: string | null;
  inputs_summary?: InputsSummary;
}

export interface ViSummary {
  scenes: number;
  first: string;
  last: string;
  max_gap_days: number | null;
}

export interface OperationUsed {
  type: 'harvest' | 'fertilization' | 'tillage' | 'baling' | 'irrigation';
  date: string;
  exported_c_tC_ha?: number | null;
  n_kg_ha?: number | null;
  organic?: boolean;
  tillage_type?: string;
  water_mm?: number | null;
}

/** What entered the balance and where it came from. */
export interface InputsSummary {
  weather_days_by_source: Record<string, number>;
  vi: Partial<Record<'NDVI' | 'OSAVI', ViSummary>>;
  soil: { source: string; soc_tC_ha: number; clay_pct: number; depth_cm: number } | null;
  operations: OperationUsed[];
  irrigated: { value: boolean | null; source: 'operations' | 'declared' | null } | null;
}

export interface CampaignList {
  parcel_id: string;
  campaigns: CampaignRow[];
}

export interface ProjectionData {
  entity_id: string;
  projection_years: number;
  reference_year: number | null;
  baseline_soc: number[];
  project_soc: number[];
  annual_delta_tC_ha_yr: number[];
  assumptions: string[];
  // Same assumptions as codes (+ params) for translation; absent from older backends.
  assumption_codes?: Array<{ code: string; year?: number }>;
  missing: MissingItem[];
}

/** Farmer-declared management: only what the platform does not record elsewhere.
 * Absent = not declared; nothing is defaulted. */
export interface ManagementData {
  harvest_export_fraction?: number | null;
  residue_removal_fraction?: number | null;
  organic_amendments_tC_ha_yr?: number | null;
  n_synthetic_kgN_ha_yr?: number | null;
  n_organic_kgN_ha_yr?: number | null;
  irrigated?: boolean | null;
  soil_lab_soc_tC_ha?: number | null;
  soil_lab_clay_pct?: number | null;
}


export interface MRVCampaign {
  year: number;
  computed_through: string | null;
  tier: number | null;
  delta_soc_tC_ha: number | null;
  n2o_tCO2eq_ha: number | null;
  co2eq_net_tCO2eq_ha: number | null;
  baseline_delta_soc_tC_ha?: number | null;
  missing: MissingItem[];
}

export interface MRVReport {
  report_id: string;
  report_type: string;
  title: string;
  standard_structure: string;
  generated_at: string;
  reporting_period_start: string | null;
  reporting_period_end: string | null;
  campaigns: MRVCampaign[];
  total_delta_soc_tC_ha: number | null;
  total_co2eq_net_tCO2eq_ha: number | null;
  baseline_reference_year: number | null;
  net_emission_reductions_tCO2eq_ha: number | null;
  // Campaigns where the project or the replayed baseline lacks a SOC change.
  baseline_incomplete_years?: number[];
  tier: number;
  certification_gaps: string[];
  assumptions: string[];
  inputs_hash: string;
}

function getTenantId(): string {
  try {
    const ctx = (window as any).__nekazariAuthContext;
    return ctx?.tenantId || '';
  } catch {
    return '';
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(options?.headers as Record<string, string> || {}) };
  const tenantId = getTenantId();
  if (tenantId && !headers['NGSILD-Tenant']) {
    headers['NGSILD-Tenant'] = tenantId;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...options,
    headers,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API error ${res.status}: ${body || res.statusText}`);
  }
  return res.json();
}

const parcelPath = (entityId: string) => `/parcels/${encodeURIComponent(entityId)}`;

export async function fetchCampaigns(entityId: string): Promise<CampaignList> {
  return apiFetch<CampaignList>(`${parcelPath(entityId)}/campaigns`);
}

export async function fetchCampaign(entityId: string, year: number): Promise<CampaignRow> {
  return apiFetch<CampaignRow>(`${parcelPath(entityId)}/campaigns/${year}`);
}

export async function calculateCampaign(entityId: string, year: number): Promise<CampaignRow> {
  return apiFetch<CampaignRow>(`${parcelPath(entityId)}/campaigns/${year}/calculate`, { method: 'POST' });
}

export async function fetchManagement(entityId: string): Promise<ManagementData> {
  return apiFetch<ManagementData>(`/parcels/${encodeURIComponent(entityId)}/management`);
}

export async function saveManagement(
  entityId: string,
  data: ManagementData,
): Promise<void> {
  await apiFetch(`/parcels/${encodeURIComponent(entityId)}/management`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export async function fetchProjection(entityId: string): Promise<ProjectionData> {
  return apiFetch<ProjectionData>(`/parcels/${encodeURIComponent(entityId)}/projection`);
}

function reportQuery(standard: string, fromYear?: number, toYear?: number): string {
  const q = new URLSearchParams({ standard });
  if (fromYear) q.set('from_year', String(fromYear));
  if (toYear) q.set('to_year', String(toYear));
  return q.toString();
}

export async function fetchMRVReport(
  entityId: string,
  standard: string = 'VM0042',
  fromYear?: number,
  toYear?: number,
): Promise<MRVReport> {
  return apiFetch<MRVReport>(`${parcelPath(entityId)}/mrv/report?${reportQuery(standard, fromYear, toYear)}`);
}

export function downloadMRVReport(entityId: string, report: MRVReport): void {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `carbon-monitoring-${report.standard_structure}-${entityId}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Tenant summary
// ---------------------------------------------------------------------------

export interface ParcelSummary {
  parcel_id: string;
  parcel_name: string;
  crop_species: string;
  campaign_year: number | null;
  computed_through: string | null;
  tier: number;
  co2_gross_tCO2_ha: number | null;
  delta_soc_tC_ha: number | null;
  co2eq_net_tCO2eq_ha: number | null;
  tier1_coverage: number | null;
}

export interface YearlyAggregation {
  year: number;
  parcel_count: number;
  co2_gross_tCO2_ha_mean: number | null;
  delta_soc_tC_ha_mean: number | null;
}

export interface TierSummaryResponse {
  tenant_id: string;
  year: number;
  parcels: ParcelSummary[];
  yearly_aggregations: YearlyAggregation[];
}

export async function fetchTenantSummary(year?: number): Promise<TierSummaryResponse> {
  const params = year ? `?year=${year}` : '';
  return apiFetch<TierSummaryResponse>(`/tenant/summary${params}`);
}
