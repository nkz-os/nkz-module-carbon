import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from '@nekazari/sdk';
import { useParams } from 'react-router-dom';
import { Select } from '@nekazari/ui-kit';
import { fetchCampaigns, calculateCampaign, fetchCampaign, fetchProjection } from '../api/carbonApi';
import type { CampaignRow, ProjectionData, CarbonPools } from '../api/carbonApi';
import CarbonTierBadge from './CarbonTierBadge';
import CarbonMissingList from './CarbonMissingList';
import CarbonProjectionChart from './CarbonProjectionChart';
import CarbonManagementForm from './CarbonManagementForm';
import CarbonMRVExport from './CarbonMRVExport';
import { colors } from './styles';
import { DASH, currentYear, fmt, fmtSigned } from './campaignFormat';

interface CarbonBottomPanelProps {
  entityId?: string;
}

function useEntityId(props: CarbonBottomPanelProps): string {
  const params = useParams<{ entityId: string }>();
  return props.entityId || params.entityId || '';
}

type TabKey = 'overview' | 'soil' | 'projection' | 'management' | 'export';

const TAB_KEYS: TabKey[] = ['overview', 'soil', 'projection', 'management', 'export'];

const POOL_KEYS: Array<{ key: keyof CarbonPools; labelKey: string; color: string }> = [
  { key: 'DPM', labelKey: 'pool_dpm', color: '#F59E0B' },
  { key: 'RPM', labelKey: 'pool_rpm', color: '#F97316' },
  { key: 'BIO', labelKey: 'pool_bio', color: '#10B981' },
  { key: 'HUM', labelKey: 'pool_hum', color: '#3B82F6' },
  { key: 'IOM', labelKey: 'pool_iom', color: '#8B5CF6' },
];

const CarbonBottomPanel: React.FC<CarbonBottomPanelProps> = (props) => {
  const { t } = useTranslation('carbon');
  const entityId = useEntityId(props);

  const [activeTab, setActiveTab] = useState<TabKey>('overview');
  const [campaigns, setCampaigns] = useState<CampaignRow[]>([]);
  const [year, setYear] = useState<number>(currentYear());
  const [row, setRow] = useState<CampaignRow | null>(null);
  const [projection, setProjection] = useState<ProjectionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [calculating, setCalculating] = useState(false);

  const loadData = useCallback(async () => {
    if (!entityId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [list, proj] = await Promise.all([
        fetchCampaigns(entityId),
        fetchProjection(entityId).catch(() => null),
      ]);
      setCampaigns(list.campaigns);
      setProjection(proj);
      const stored = list.campaigns.find((c) => c.campaign_label === year);
      setRow(stored ? await fetchCampaign(entityId, year) : null);
    } catch {
      setError(t('error_loading'));
    } finally {
      setLoading(false);
    }
  }, [entityId, year, t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCalculate = useCallback(async () => {
    if (!entityId) return;
    setCalculating(true);
    setError(null);
    try {
      setRow(await calculateCampaign(entityId, year));
      const [list, proj] = await Promise.all([
        fetchCampaigns(entityId),
        fetchProjection(entityId).catch(() => null),
      ]);
      setCampaigns(list.campaigns);
      setProjection(proj);
    } catch {
      setError(t('error_loading'));
    } finally {
      setCalculating(false);
    }
  }, [entityId, year, t]);

  const yearOptions = useMemo(() => {
    const years = new Set<number>([currentYear(), ...campaigns.map((c) => c.campaign_label)]);
    return Array.from(years).sort((a, b) => b - a).map((y) => ({ value: String(y), label: String(y) }));
  }, [campaigns]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '400px',
        color: colors.textMuted, fontSize: '14px' }}>
        {t('loading')}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '400px', overflow: 'hidden', boxSizing: 'border-box' }}>
      <div style={{ display: 'flex', borderBottom: `1px solid ${colors.border}`, backgroundColor: colors.bgSurface,
        overflowX: 'auto', flexShrink: 0 }}>
        {TAB_KEYS.map((key) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              padding: '10px 16px',
              border: 'none',
              borderBottom: activeTab === key ? `2px solid ${colors.accentBase}` : '2px solid transparent',
              backgroundColor: activeTab === key ? colors.accentSoft : 'transparent',
              color: activeTab === key ? colors.accentBase : colors.textSecondary,
              fontSize: '13px',
              fontWeight: activeTab === key ? 600 : 400,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            {t(key === 'soil' ? 'pools' : key === 'export' ? 'export_report' : key)}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
        {error && (
          <div style={{ marginBottom: '8px', color: colors.danger, fontSize: '13px' }}>{error}</div>
        )}

        {activeTab === 'overview' && (
          <OverviewTab
            row={row}
            year={year}
            yearOptions={yearOptions}
            onYear={(v) => setYear(Number(v))}
            onCalculate={handleCalculate}
            calculating={calculating}
            t={t}
          />
        )}

        {activeTab === 'soil' && <SoilTab row={row} t={t} />}

        {activeTab === 'projection' && <ProjectionTab projection={projection} t={t} />}

        {activeTab === 'management' && (
          <div>
            <SectionLabel text={t('management')} />
            <CarbonManagementForm entityId={entityId} onSaved={loadData} />
          </div>
        )}

        {activeTab === 'export' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <SectionLabel text={t('export_report')} />
            <CarbonMRVExport entityId={entityId} years={campaigns.map((c) => c.campaign_label)} />
          </div>
        )}
      </div>
    </div>
  );
};

/* ========== Tab sub-components ========== */

function OverviewTab({
  row,
  year,
  yearOptions,
  onYear,
  onCalculate,
  calculating,
  t,
}: {
  row: CampaignRow | null;
  year: number;
  yearOptions: { value: string; label: string }[];
  onYear: (v: string) => void;
  onCalculate: () => void;
  calculating: boolean;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const header = (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
      <div style={{ width: '120px' }}>
        <Select value={String(year)} onValueChange={onYear} options={yearOptions} size="sm" />
      </div>
      {row && <CarbonTierBadge tier={row.data_tier} compact />}
      <span style={{ fontSize: '12px', color: colors.textSecondary }}>
        {row?.computed_through ? `${t('computed_through')}: ${row.computed_through}` : t('campaign_not_computed')}
      </span>
      <button
        onClick={onCalculate}
        disabled={calculating}
        style={{
          marginLeft: 'auto',
          padding: '6px 14px',
          border: 'none',
          borderRadius: '6px',
          backgroundColor: calculating ? colors.gray300 : colors.accentBase,
          color: '#FFFFFF',
          fontSize: '13px',
          cursor: calculating ? 'not-allowed' : 'pointer',
        }}
      >
        {calculating ? t('calculating') : t('recalculate')}
      </button>
    </div>
  );

  if (!row) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {header}
        <div style={{ fontSize: '14px', color: colors.textSecondary }}>{t('no_data')}</div>
      </div>
    );
  }

  const metrics = [
    { label: t('co2_gross'), value: fmt(row.co2_sequestered_gross), unit: t('units.tCO2_ha') },
    {
      label: t('soilCarbonDelta'),
      value: fmtSigned(row.soil_carbon_delta),
      unit: row.soil_carbon_delta_ci95 !== undefined
        ? `${t('units.tC_ha')} ± ${fmt(row.soil_carbon_delta_ci95)}`
        : t('units.tC_ha'),
    },
    { label: t('co2eq_net'), value: fmtSigned(row.co2eq_net), unit: t('units.tCO2eq_ha') },
    { label: t('cover_days'), value: String(row.cover_days), unit: `${t('bare_days')}: ${row.bare_days}` },
    { label: t('tier1_coverage'), value: `${Math.round(row.tier1_coverage * 100)}%`, unit: '' },
    { label: t('n2o'), value: fmt(row.n2o_emissions, 3), unit: t('units.tCO2eq_ha') },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {header}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '8px' }}>
        {metrics.map((m) => (
          <MetricCard key={m.label} label={m.label} value={m.value} unit={m.unit} />
        ))}
      </div>

      {row.cycle_breakdown.length > 0 && (
        <div>
          <SectionLabel text={t('cycles')} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {row.cycle_breakdown.map((c) => (
              <div key={c.crop_id} style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', fontSize: '12px',
                color: colors.textPrimary, padding: '6px 8px', backgroundColor: colors.bgSubtle, borderRadius: '6px' }}>
                <strong>{c.species}</strong>
                <span>{t(`role.${c.role}`, { defaultValue: c.role })}</span>
                <span>{c.start} → {c.end ?? DASH}</span>
                <span>{t('days_computed', { done: c.days_computed, total: c.days_in_period })}</span>
                <span>{t('to_soil')}: {fmt(c.c_to_soil_tC_ha)} {t('units.tC_ha')}</span>
                <span>{t('exported')}: {fmt(c.exported_c_tC_ha)} {t('units.tC_ha')}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <SectionLabel text={t('missing_title')} />
        <CarbonMissingList missing={row.missing} />
      </div>

      {row.data_sources.length > 0 && (
        <div>
          <SectionLabel text={t('data_sources')} />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {row.data_sources.map((src) => (
              <span key={src} style={{ padding: '2px 8px', backgroundColor: colors.bgMuted, borderRadius: '4px',
                fontSize: '11px', color: colors.textSecondary }}>
                {src}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SoilTab({ row, t }: { row: CampaignRow | null; t: (key: string) => string }) {
  const pools = row?.pools_end;
  if (!row || !pools) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 20px', color: colors.textMuted, fontSize: '14px' }}>
        {t('no_soil_balance')}
      </div>
    );
  }
  const maxPool = Math.max(...POOL_KEYS.map((p) => pools[p.key]), 1);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <SectionLabel text={`${t('pools')} (${row.pools_state_date ?? DASH})`} />
        {POOL_KEYS.map((pool) => {
          const val = pools[pool.key];
          return (
            <div key={pool.key} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ width: '80px', fontSize: '11px', color: colors.textSecondary, flexShrink: 0, textAlign: 'right' }}>
                {t(pool.labelKey)}
              </span>
              <div style={{ flex: 1, height: '16px', backgroundColor: colors.bgMuted, borderRadius: '8px', overflow: 'hidden', minWidth: 0 }}>
                <div style={{ height: '100%', width: `${Math.max((val / maxPool) * 100, 2)}%`, backgroundColor: pool.color, borderRadius: '8px' }} />
              </div>
              <span style={{ width: '60px', fontSize: '11px', fontWeight: 500, color: colors.textPrimary, textAlign: 'right', flexShrink: 0 }}>
                {val.toFixed(2)}
              </span>
            </div>
          );
        })}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '8px' }}>
        <MetricCard label={t('soc_start')} value={fmt(row.soc_start)} unit={t('units.tC_ha')} />
        <MetricCard label={t('soc_end')} value={fmt(row.soc_end)} unit={t('units.tC_ha')} />
        <MetricCard label={t('soilCarbonDelta')} value={fmtSigned(row.soil_carbon_delta)} unit={t('units.tC_ha')} />
      </div>
    </div>
  );
}

function ProjectionTab({ projection, t }: { projection: ProjectionData | null; t: (key: string) => string }) {
  if (!projection || projection.project_soc.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div style={{ textAlign: 'center', padding: '24px 20px', color: colors.textMuted, fontSize: '14px' }}>
          {t('no_projection')}
        </div>
        {projection && <CarbonMissingList missing={projection.missing} />}
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <SectionLabel text={t('projection')} />
      <CarbonProjectionChart data={projection} />
      {projection.assumptions.length > 0 && (
        <div>
          <SectionLabel text={t('assumptions')} />
          <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '12px', color: colors.textSecondary }}>
            {projection.assumptions.map((a) => <li key={a}>{a}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ========== Shared UI helpers ========== */

function MetricCard({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div style={{ padding: '10px 12px', backgroundColor: colors.bgSubtle, borderRadius: '8px',
      border: `1px solid ${colors.border}`, minWidth: 0 }}>
      <div style={{ fontSize: '11px', color: colors.textMuted, marginBottom: '2px' }}>{label}</div>
      <div style={{ fontSize: '18px', fontWeight: 600, color: colors.textPrimary, lineHeight: 1.2 }}>{value}</div>
      {unit && <div style={{ fontSize: '11px', color: colors.textMuted, marginTop: '1px' }}>{unit}</div>}
    </div>
  );
}

function SectionLabel({ text }: { text: string }) {
  return (
    <div style={{ fontSize: '11px', fontWeight: 600, color: colors.textSecondary, textTransform: 'uppercase',
      letterSpacing: '0.5px', marginBottom: '8px' }}>
      {text}
    </div>
  );
}

export default CarbonBottomPanel;
