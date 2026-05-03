import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from '@nekazari/sdk';
import { useParams } from 'react-router-dom';
import { fetchAssessment } from '../api/carbonApi';
import type { CarbonAssessment } from '../api/carbonApi';
import CarbonTierBadge from './CarbonTierBadge';

interface CarbonDashboardWidgetProps {
  entityId?: string;
}

function useEntityId(props: CarbonDashboardWidgetProps): string {
  const params = useParams<{ entityId: string }>();
  return props.entityId || params.entityId || '';
}

const CarbonDashboardWidget: React.FC<CarbonDashboardWidgetProps> = (props) => {
  const { t } = useTranslation('carbon');
  const entityId = useEntityId(props);

  const [assessment, setAssessment] = useState<CarbonAssessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!entityId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAssessment(entityId);
      setAssessment(data);
    } catch (err) {
      setError(t('error_loading'));
    } finally {
      setLoading(false);
    }
  }, [entityId, t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          minHeight: '120px',
          color: '#9CA3AF',
          fontSize: '13px',
        }}
      >
        {t('loading')}
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '8px',
          height: '100%',
          minHeight: '120px',
          padding: '16px',
        }}
      >
        <div style={{ color: '#DC2626', fontSize: '13px', textAlign: 'center' }}>{error}</div>
        <button
          onClick={loadData}
          style={{
            padding: '6px 14px',
            border: '1px solid #D1D5DB',
            borderRadius: '6px',
            backgroundColor: '#FFFFFF',
            color: '#374151',
            fontSize: '12px',
            cursor: 'pointer',
          }}
        >
          {t('retry')}
        </button>
      </div>
    );
  }

  if (!assessment) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          minHeight: '120px',
          padding: '16px',
          textAlign: 'center',
          color: '#6B7280',
          fontSize: '13px',
        }}
      >
        {t('no_data')}
      </div>
    );
  }

  const co2Cumulative = assessment.co2_sequestered_cumulative;
  const gppDaily = assessment.gpp_daily;
  const socDelta = assessment.soil_carbon_delta;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        padding: '12px',
        height: '100%',
        boxSizing: 'border-box',
        minWidth: 0,
      }}
    >
      {/* Top row: Title + Tier */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            fontSize: '14px',
            fontWeight: 600,
            color: '#111827',
          }}
        >
          {t('title')}
        </span>
        <CarbonTierBadge tier={assessment.tier} confidence={assessment.confidence} compact />
      </div>

      {/* KPI cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(90px, 1fr))',
          gap: '8px',
        }}
      >
        <DashboardKPI
          label={t('co2SequesteredCumulative')}
          value={co2Cumulative.value.toFixed(1)}
          unit={co2Cumulative.unit}
          trend={co2Cumulative.value > 0 ? 'up' : 'neutral'}
        />
        <DashboardKPI
          label={t('gppDaily')}
          value={gppDaily.value.toFixed(2)}
          unit={gppDaily.unit}
          trend="neutral"
        />
        <DashboardKPI
          label={t('soilCarbonDelta')}
          value={
            socDelta
              ? `${socDelta.value > 0 ? '+' : ''}${socDelta.value.toFixed(2)}`
              : '--'
          }
          unit={socDelta?.unit ?? t('units.tC_ha_yr')}
          trend={socDelta && socDelta.value > 0 ? 'up' : socDelta && socDelta.value < 0 ? 'down' : 'neutral'}
        />
      </div>

      {/* Sparkline indicator */}
      {co2Cumulative.value > 0 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '11px',
            color: '#059669',
          }}
        >
          <svg width="40" height="16" viewBox="0 0 40 16" fill="none">
            <path
              d="M0 14L8 10L16 12L24 6L32 8L40 2"
              stroke="#059669"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
            <path
              d="M0 14L8 10L16 12L24 6L32 8L40 2"
              stroke="#059669"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
              opacity="0.15"
            />
          </svg>
          <span>{t('co2SequesteredCumulative')} {'>'}</span>
        </div>
      )}
    </div>
  );
};

function DashboardKPI({
  label,
  value,
  unit,
  trend,
}: {
  label: string;
  value: string;
  unit: string;
  trend: 'up' | 'down' | 'neutral';
}) {
  const trendColor = trend === 'up' ? '#059669' : trend === 'down' ? '#DC2626' : '#6B7280';

  return (
    <div
      style={{
        padding: '8px',
        backgroundColor: '#F9FAFB',
        borderRadius: '6px',
        border: '1px solid #E5E7EB',
        minWidth: 0,
      }}
    >
      <div
        style={{
          fontSize: '10px',
          color: '#9CA3AF',
          marginBottom: '2px',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: '16px',
          fontWeight: 600,
          color: '#111827',
          lineHeight: 1.2,
          display: 'flex',
          alignItems: 'baseline',
          gap: '4px',
        }}
      >
        {value}
        {trend !== 'neutral' && (
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{ flexShrink: 0 }}>
            {trend === 'up' ? (
              <path d="M5 2L9 8H1L5 2Z" fill={trendColor} />
            ) : (
              <path d="M5 8L1 2H9L5 8Z" fill={trendColor} />
            )}
          </svg>
        )}
      </div>
      <div
        style={{
          fontSize: '9px',
          color: '#9CA3AF',
        }}
      >
        {unit}
      </div>
    </div>
  );
}

export default CarbonDashboardWidget;
