import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation, useViewerOptional } from '@nekazari/sdk';
import { useParams } from 'react-router-dom';
import { MetricCard, MetricGrid, Spinner } from '@nekazari/ui-kit';
import { fetchAssessment } from '../api/carbonApi';
import type { CarbonAssessment } from '../api/carbonApi';
import CarbonTierBadge from './CarbonTierBadge';
import { colors } from './styles';

interface CarbonDashboardWidgetProps {
  entityId?: string;
}

function useEntityId(props: CarbonDashboardWidgetProps): string {
  const viewer = useViewerOptional();
  const params = useParams<{ entityId: string }>();

  if (viewer?.selectedEntityId) {
    const id = viewer.selectedEntityId;
    return id.includes(':') ? id.split(':').pop()! : id;
  }

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
      <div style={{ display: 'flex', justifyContent: 'center', padding: '24px' }}>
        <Spinner size="sm" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '16px', textAlign: 'center', color: colors.danger, fontSize: '13px' }}>
        {error}
      </div>
    );
  }

  if (!assessment) {
    return (
      <div style={{ padding: '16px', textAlign: 'center', color: colors.textSecondary, fontSize: '13px' }}>
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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
        <span style={{ fontSize: '14px', fontWeight: 600, color: colors.textPrimary }}>{t('title')}</span>
        <CarbonTierBadge tier={assessment.tier} confidence={assessment.confidence} compact />
      </div>

      <MetricGrid columns={3}>
        <MetricCard
          label={t('co2SequesteredCumulative')}
          value={co2Cumulative.value.toFixed(1)}
          unit={co2Cumulative.unit}
        />
        <MetricCard
          label={t('gppDaily')}
          value={gppDaily.value.toFixed(2)}
          unit={gppDaily.unit}
        />
        <MetricCard
          label={t('soilCarbonDelta')}
          value={
            socDelta
              ? `${socDelta.value > 0 ? '+' : ''}${socDelta.value.toFixed(2)}`
              : '--'
          }
          unit={socDelta?.unit ?? t('units.tC_ha_yr')}
        />
      </MetricGrid>

      {co2Cumulative.value > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: colors.accentBase }}>
          <svg width="40" height="16" viewBox="0 0 40 16" fill="none">
            <path d="M0 14L8 10L16 12L24 6L32 8L40 2" stroke="#059669" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
          </svg>
          <span>{t('co2SequesteredCumulative')}</span>
        </div>
      )}
    </div>
  );
};

export default CarbonDashboardWidget;
