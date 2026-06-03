// Resolve API base URL safely for both browser (import.meta.env) and
// Node.js CJS manifest-emit context (process.env).
const API_BASE = (typeof process !== 'undefined' && process.env?.VITE_API_URL)
  || (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL)
  ? `${
      (typeof process !== 'undefined' && process.env?.VITE_API_URL)
      || (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL)
    }/api/carbon`
  : '/api/carbon';

export interface CarbonValue {
  value: number;
  unit: string;
}

export interface CarbonPools {
  dpm_tC_ha: number;
  rpm_tC_ha: number;
  bio_tC_ha: number;
  hum_tC_ha: number;
  iom_tC_ha: number;
  total_tC_ha: number;
}

export interface CarbonAssessment {
  entity_id: string;
  assessment_date: string;
  tier: number;
  methodology: string;
  confidence: number;
  confidence_interval_pct: number;
  gpp_daily: CarbonValue;
  npp_daily: CarbonValue;
  co2_sequestered_daily: CarbonValue;
  co2_sequestered_cumulative: CarbonValue;
  agb_dry: CarbonValue;
  bgb_dry: CarbonValue;
  soil_carbon_delta: CarbonValue | null;
  carbon_stock_total: CarbonValue | null;
  pools: CarbonPools | null;
  co2eq_net_daily: CarbonValue | null;
  co2eq_net_cumulative: CarbonValue | null;
  gwp_standard: string;
  missing_for_next_tier: string[];
  data_sources: string[];
  data_provenance: Record<string, string>;
}

export interface GapItem {
  source: string;
  missing: boolean;
  action: string;
  auto_fill: string | null;
}

export interface TierInfo {
  current_tier: number;
  confidence: number;
  available_data: string[];
  gaps: GapItem[];
}

export interface ProjectionData {
  entity_id: string;
  projection_years: number;
  baseline_soc: number[];
  project_soc: number[];
  annual_delta_tC_ha_yr: number[];
}

export interface ManagementData {
  tillage_type?: string;
  residues_removed?: boolean;
  cover_crop_months?: number;
  organic_amendments_tC_ha_yr?: number;
  n_synthetic_kgN_ha_yr?: number;
  n_organic_kgN_ha_yr?: number;
  irrigated?: boolean;
  soil_lab_soc_tC_ha?: number | null;
  soil_lab_clay_pct?: number | null;
  harvest_export_fraction?: number;
  weather_source?: string;
  weather_sensor_id?: string;
}

export interface SensorInfo {
  id: string;
  name: string;
  sensor_type: string;
  latitude: number | null;
  longitude: number | null;
}

export interface MRVReport {
  standard: string;
  generated_at: string;
  entity_id: string;
  tier: number;
  methodology: string;
  net_emission_reductions: number;
  verified_credits: number;
  buffer_pool: number;
  crediting_period_start: string;
  crediting_period_end: string;
  leakage: number;
  uncertainty_deduction: number;
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

export async function fetchAssessment(entityId: string): Promise<CarbonAssessment> {
  return apiFetch<CarbonAssessment>(`/parcels/${encodeURIComponent(entityId)}/assessment`);
}

export async function fetchTierInfo(entityId: string): Promise<TierInfo> {
  return apiFetch<TierInfo>(`/parcels/${encodeURIComponent(entityId)}/tier-info`);
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

export async function triggerCalculation(
  entityId: string,
  options?: {
    crop_species?: string;
    lat?: number;
    lon?: number;
    management?: ManagementData;
  },
): Promise<CarbonAssessment> {
  return apiFetch<CarbonAssessment>(`/parcels/${encodeURIComponent(entityId)}/calculate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      entity_id: entityId,
      crop_species: options?.crop_species,
      lat: options?.lat,
      lon: options?.lon,
      management: options?.management,
    }),
  });
}

export async function fetchProjection(entityId: string): Promise<ProjectionData> {
  return apiFetch<ProjectionData>(`/parcels/${encodeURIComponent(entityId)}/projection`);
}

export async function fetchMRVReport(
  entityId: string,
  standard: string = 'VM0042',
): Promise<MRVReport> {
  return apiFetch<MRVReport>(
    `/parcels/${encodeURIComponent(entityId)}/mrv/report?standard=${encodeURIComponent(standard)}`,
  );
}

export async function downloadMRVReport(
  entityId: string,
  standard: string = 'VM0042',
): Promise<void> {
  const report = await fetchMRVReport(entityId, standard);
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `carbon-mrv-${standard}-${entityId}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Sensor listing
// ---------------------------------------------------------------------------

export async function fetchAvailableSensors(entityId: string): Promise<SensorInfo[]> {
  return apiFetch<SensorInfo[]>(`/sensors/available?entity_id=${encodeURIComponent(entityId)}`);
}

// ---------------------------------------------------------------------------
// Tenant summary
// ---------------------------------------------------------------------------

export interface ParcelSummary {
  parcel_id: string;
  parcel_name: string;
  crop_species: string;
  co2_captured_cumulative: number;
  carbon_stock_total: number;
  tier: number;
  methodology: string;
  last_calculation_date: string | null;
}

export interface YearlyAggregation {
  year: number;
  total_co2_captured_kg: number;
  avg_carbon_stock_tC_ha: number;
  parcel_count: number;
}

export interface TierSummaryResponse {
  tenant_id: string;
  parcels: ParcelSummary[];
  yearly_aggregations: YearlyAggregation[];
}

export async function fetchTenantSummary(year?: number): Promise<TierSummaryResponse> {
  const params = year ? `?year=${year}` : '';
  return apiFetch<TierSummaryResponse>(`/tenant/summary${params}`);
}
