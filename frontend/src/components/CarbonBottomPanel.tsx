import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from '@nekazari/sdk';
import { useParams } from 'react-router-dom';
import { fetchAssessment, fetchTierInfo, fetchProjection, triggerCalculation, fetchManagement } from '../api/carbonApi';
import type { CarbonAssessment, TierInfo, ProjectionData } from '../api/carbonApi';
import CarbonTierBadge from './CarbonTierBadge';
import CarbonGapList from './CarbonGapList';
import CarbonProjectionChart from './CarbonProjectionChart';
import CarbonManagementForm from './CarbonManagementForm';
import CarbonMRVExport from './CarbonMRVExport';


interface CarbonBottomPanelProps {
  entityId?: string;
}

function useEntityId(props: CarbonBottomPanelProps): string {
  const params = useParams<{ entityId: string }>();
  return props.entityId || params.entityId || '';
}

type TabKey = 'overview' | 'soil' | 'projection' | 'management' | 'export';

const TAB_KEYS: TabKey[] = ['overview', 'soil', 'projection', 'management', 'export'];

const POOL_KEYS: Array<{ key: string; labelKey: string; color: string }> = [
  { key: 'dpm', labelKey: 'pool_dpm', color: '#F59E0B' },
  { key: 'rpm', labelKey: 'pool_rpm', color: '#F97316' },
  { key: 'bio', labelKey: 'pool_bio', color: '#10B981' },
  { key: 'hum', labelKey: 'pool_hum', color: '#3B82F6' },
  { key: 'iom', labelKey: 'pool_iom', color: '#8B5CF6' },
];

const CarbonBottomPanel: React.FC<CarbonBottomPanelProps> = (props) => {
  const { t } = useTranslation('carbon');
  const entityId = useEntityId(props);

  const [activeTab, setActiveTab] = useState<TabKey>('overview');
  const [assessment, setAssessment] = useState<CarbonAssessment | null>(null);
  const [tierInfo, setTierInfo] = useState<TierInfo | null>(null);
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
      const [assess, info, proj] = await Promise.all([
        fetchAssessment(entityId).catch(() => null),
        fetchTierInfo(entityId).catch(() => null),
        fetchProjection(entityId).catch(() => null),
      ]);
      if (assess) setAssessment(assess);
      if (info) setTierInfo(info);
      if (proj) setProjection(proj);
    } catch (err) {
      setError(t('error_loading'));
    } finally {
      setLoading(false);
    }
  }, [entityId, t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCalculate = useCallback(async () => {
    if (!entityId) return;
    setCalculating(true);
    setError(null);
    try {
      let mgmtData = undefined;
      try {
        mgmtData = await fetchManagement(entityId);
      } catch { /* no management saved yet */ }
      const result = await triggerCalculation(entityId, { management: mgmtData });
      setAssessment(result);
      const proj = await fetchProjection(entityId).catch(() => null);
      if (proj) setProjection(proj);
      const info = await fetchTierInfo(entityId).catch(() => null);
      if (info) setTierInfo(info);
    } catch (err) {
      setError(t('error_loading'));
    } finally {
      setCalculating(false);
    }
  }, [entityId, t]);

  const handleManagementSaved = useCallback(() => {
    // Reload assessment and projection after management save
    loadData();
  }, [loadData]);

  // Loading state
  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '400px',
          color: '#9CA3AF',
          fontSize: '14px',
        }}
      >
        {t('loading')}
      </div>
    );
  }

  // Error state
  if (error && !assessment) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '12px',
          height: '400px',
          padding: '24px',
        }}
      >
        <div style={{ color: '#DC2626', fontSize: '14px', textAlign: 'center' }}>{error}</div>
        <button
          onClick={loadData}
          style={{
            padding: '8px 20px',
            border: '1px solid #D1D5DB',
            borderRadius: '6px',
            backgroundColor: '#FFFFFF',
            color: '#374151',
            fontSize: '13px',
            cursor: 'pointer',
          }}
        >
          {t('retry')}
        </button>
      </div>
    );
  }

  // Empty state (no assessment yet)
  if (!assessment) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '16px',
          height: '400px',
          padding: '24px',
          textAlign: 'center',
        }}
      >
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
          <circle cx="24" cy="24" r="22" fill="#E5E7EB" />
          <path d="M16 32L24 16L32 32H16Z" fill="#9CA3AF" />
        </svg>
        <div style={{ fontSize: '14px', color: '#6B7280', maxWidth: '300px', lineHeight: 1.5 }}>
          {t('no_data')}
        </div>
        <button
          onClick={handleCalculate}
          disabled={calculating}
          style={{
            padding: '10px 24px',
            border: 'none',
            borderRadius: '8px',
            backgroundColor: calculating ? '#9CA3AF' : '#059669',
            color: '#FFFFFF',
            fontSize: '14px',
            fontWeight: 500,
            cursor: calculating ? 'not-allowed' : 'pointer',
          }}
        >
          {calculating ? t('calculating') : t('calculate')}
        </button>
      </div>
    );
  }

  const pools = assessment.pools;
  const maxPoolValue = pools
    ? Math.max(
        pools.dpm_tC_ha,
        pools.rpm_tC_ha,
        pools.bio_tC_ha,
        pools.hum_tC_ha,
        pools.iom_tC_ha,
        1,
      )
    : 1;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '400px',
        overflow: 'hidden',
        boxSizing: 'border-box',
      }}
    >
      {/* Tab bar */}
      <div
        style={{
          display: 'flex',
          borderBottom: '1px solid #E5E7EB',
          backgroundColor: '#FFFFFF',
          overflowX: 'auto',
          flexShrink: 0,
        }}
      >
        {TAB_KEYS.map((key) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              padding: '10px 16px',
              border: 'none',
              borderBottom: activeTab === key ? '2px solid #059669' : '2px solid transparent',
              backgroundColor: activeTab === key ? '#F0FDF4' : 'transparent',
              color: activeTab === key ? '#059669' : '#6B7280',
              fontSize: '13px',
              fontWeight: activeTab === key ? 600 : 400,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              transition: 'all 0.15s ease',
              flexShrink: 0,
            }}
          >
            {t(key === 'soil' ? 'pools' : key === 'export' ? 'export_report' : key)}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '12px',
        }}
      >
        {activeTab === 'overview' && (
          <OverviewTab assessment={assessment} tierInfo={tierInfo} t={t} />
        )}

        {activeTab === 'soil' && pools && (
          <SoilTab
            pools={pools}
            maxPoolValue={maxPoolValue}
            carbonStockTotal={assessment.carbon_stock_total}
            soilCarbonDelta={assessment.soil_carbon_delta}
            t={t}
          />
        )}

        {activeTab === 'soil' && !pools && (
          <div
            style={{
              textAlign: 'center',
              padding: '40px 20px',
              color: '#9CA3AF',
              fontSize: '14px',
            }}
          >
            {t('no_data')}
          </div>
        )}

        {activeTab === 'projection' && (
          <ProjectionTab projection={projection} t={t} />
        )}

        {activeTab === 'management' && (
          <ManagementTab
            entityId={entityId}
            assessment={assessment}
            onSaved={handleManagementSaved}
            t={t}
          />
        )}

        {activeTab === 'export' && (
          <ExportTab entityId={entityId} assessment={assessment} t={t} />
        )}
      </div>
    </div>
  );
};

/* ========== Tab sub-components ========== */

function OverviewTab({
  assessment,
  tierInfo,
  t,
}: {
  assessment: CarbonAssessment;
  tierInfo: TierInfo | null;
  t: (key: string) => string;
}) {
  const gaps = tierInfo?.gaps || [];

  const metrics = [
    { label: t('tier'), value: `T${assessment.tier}`, sub: assessment.methodology },
    { label: t('confidence'), value: `${assessment.confidence.toFixed(1)}%`, sub: `+/- ${assessment.confidence_interval_pct.toFixed(0)}%` },
    { label: t('gppDaily'), value: `${assessment.gpp_daily.value.toFixed(2)}`, unit: assessment.gpp_daily.unit },
    { label: t('nppDaily'), value: `${assessment.npp_daily.value.toFixed(2)}`, unit: assessment.npp_daily.unit },
    { label: t('co2SequesteredDaily'), value: `${assessment.co2_sequestered_daily.value.toFixed(2)}`, unit: assessment.co2_sequestered_daily.unit },
    { label: t('co2SequesteredCumulative'), value: `${assessment.co2_sequestered_cumulative.value.toFixed(1)}`, unit: assessment.co2_sequestered_cumulative.unit },
    { label: t('agbDry'), value: `${assessment.agb_dry.value.toFixed(2)}`, unit: assessment.agb_dry.unit },
    { label: t('bgbDry'), value: `${assessment.bgb_dry.value.toFixed(2)}`, unit: assessment.bgb_dry.unit },
    { label: t('soilCarbonDelta'), value: assessment.soil_carbon_delta ? `${assessment.soil_carbon_delta.value > 0 ? '+' : ''}${assessment.soil_carbon_delta.value.toFixed(2)}` : '--', unit: assessment.soil_carbon_delta?.unit ?? t('units.tC_ha_yr') },
    { label: t('carbonStockTotal'), value: assessment.carbon_stock_total ? `${assessment.carbon_stock_total.value.toFixed(1)}` : '--', unit: assessment.carbon_stock_total?.unit ?? t('units.tC_ha') },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Metric grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
          gap: '8px',
        }}
      >
        {metrics.map((m, i) => (
          <MetricCard key={i} label={m.label} value={m.value} unit={m.unit} sub={m.sub} />
        ))}
      </div>

      {/* Data sources */}
      {assessment.data_sources.length > 0 && (
        <div>
          <SectionLabel text={t('data_sources')} />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {assessment.data_sources.map((src, i) => (
              <span
                key={i}
                style={{
                  padding: '2px 8px',
                  backgroundColor: '#F3F4F6',
                  borderRadius: '4px',
                  fontSize: '11px',
                  color: '#6B7280',
                }}
              >
                {src}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Gaps */}
      {gaps.length > 0 && (
        <div>
          <SectionLabel text={t('gaps')} />
          <CarbonGapList gaps={gaps} missingForNextTier={assessment.missing_for_next_tier} />
        </div>
      )}
    </div>
  );
}

function SoilTab({
  pools,
  maxPoolValue,
  carbonStockTotal,
  soilCarbonDelta,
  t,
}: {
  pools: { dpm_tC_ha: number; rpm_tC_ha: number; bio_tC_ha: number; hum_tC_ha: number; iom_tC_ha: number; total_tC_ha: number };
  maxPoolValue: number;
  carbonStockTotal: { value: number; unit: string } | null;
  soilCarbonDelta: { value: number; unit: string } | null;
  t: (key: string) => string;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Pool bars */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <SectionLabel text={t('pools')} />
        {POOL_KEYS.map((pool) => {
          const val = pools[`${pool.key}_tC_ha` as keyof typeof pools] as number;
          const pct = (val / maxPoolValue) * 100;
          return (
            <div key={pool.key} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span
                style={{
                  width: '80px',
                  fontSize: '11px',
                  color: '#6B7280',
                  flexShrink: 0,
                  textAlign: 'right',
                }}
              >
                {t(pool.labelKey)}
              </span>
              <div
                style={{
                  flex: 1,
                  height: '16px',
                  backgroundColor: '#F3F4F6',
                  borderRadius: '8px',
                  overflow: 'hidden',
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    height: '100%',
                    width: `${Math.max(pct, 2)}%`,
                    backgroundColor: pool.color,
                    borderRadius: '8px',
                    transition: 'width 0.3s ease',
                  }}
                />
              </div>
              <span
                style={{
                  width: '60px',
                  fontSize: '11px',
                  fontWeight: 500,
                  color: '#374151',
                  textAlign: 'right',
                  flexShrink: 0,
                }}
              >
                {val.toFixed(2)}
              </span>
            </div>
          );
        })}
      </div>

      {/* Total stock */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
          gap: '8px',
        }}
      >
        <MetricCard
          label={t('carbonStockTotal')}
          value={carbonStockTotal?.value.toFixed(2) ?? pools.total_tC_ha.toFixed(2)}
          unit={carbonStockTotal?.unit ?? t('units.tC_ha')}
        />
        <MetricCard
          label={t('soilCarbonDelta')}
          value={soilCarbonDelta ? `${soilCarbonDelta.value > 0 ? '+' : ''}${soilCarbonDelta.value.toFixed(2)}` : '--'}
          unit={soilCarbonDelta?.unit ?? t('units.tC_ha_yr')}
        />
      </div>
    </div>
  );
}

function ProjectionTab({
  projection,
  t,
}: {
  projection: ProjectionData | null;
  t: (key: string) => string;
}) {
  if (!projection) {
    return (
      <div
        style={{
          textAlign: 'center',
          padding: '40px 20px',
          color: '#9CA3AF',
          fontSize: '14px',
        }}
      >
        {t('no_data')}
      </div>
    );
  }

  return (
    <div>
      <SectionLabel text={t('projection')} />
      <CarbonProjectionChart data={projection} />
    </div>
  );
}

function ManagementTab({
  entityId,
  assessment,
  onSaved,
  t,
}: {
  entityId: string;
  assessment: CarbonAssessment;
  onSaved: () => void;
  t: (key: string) => string;
}) {
  return (
    <div>
      <SectionLabel text={t('management')} />
      <CarbonManagementForm entityId={entityId} onSaved={onSaved} />
    </div>
  );
}

function ExportTab({
  entityId,
  assessment,
  t,
}: {
  entityId: string;
  assessment: CarbonAssessment;
  t: (key: string) => string;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <SectionLabel text={t('export_report')} />
      <CarbonMRVExport entityId={entityId} />
    </div>
  );
}

/* ========== Shared UI helpers ========== */

function MetricCard({
  label,
  value,
  unit,
  sub,
}: {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
}) {
  return (
    <div
      style={{
        padding: '10px 12px',
        backgroundColor: '#F9FAFB',
        borderRadius: '8px',
        border: '1px solid #E5E7EB',
        minWidth: 0,
      }}
    >
      <div
        style={{
          fontSize: '11px',
          color: '#9CA3AF',
          marginBottom: '2px',
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: '18px',
          fontWeight: 600,
          color: '#111827',
          lineHeight: 1.2,
        }}
      >
        {value}
      </div>
      {(unit || sub) && (
        <div
          style={{
            fontSize: '11px',
            color: '#9CA3AF',
            marginTop: '1px',
          }}
        >
          {unit || sub}
        </div>
      )}
    </div>
  );
}

function SectionLabel({ text }: { text: string }) {
  return (
    <div
      style={{
        fontSize: '11px',
        fontWeight: 600,
        color: '#6B7280',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        marginBottom: '8px',
      }}
    >
      {text}
    </div>
  );
}

export default CarbonBottomPanel;
