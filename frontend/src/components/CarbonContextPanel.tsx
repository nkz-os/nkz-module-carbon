import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from '@nekazari/sdk';
import { useParams } from 'react-router-dom';
import { EmptyState, Button, Spinner } from '@nekazari/ui-kit';
import { fetchAssessment, fetchTierInfo, triggerCalculation } from '../api/carbonApi';
import type { CarbonAssessment, TierInfo } from '../api/carbonApi';
import CarbonTierBadge from './CarbonTierBadge';
import CarbonGapList from './CarbonGapList';
import { getManagementData } from '../hooks/useCarbonState';

interface CarbonContextPanelProps {
  entityId?: string;
  managementData?: import('../api/carbonApi').ManagementData | null;
}

function useEntityId(props: CarbonContextPanelProps): string {
  const params = useParams<{ entityId: string }>();
  return props.entityId || params.entityId || '';
}

const CarbonContextPanel: React.FC<CarbonContextPanelProps> = (props) => {
  const { t } = useTranslation('carbon');
  const entityId = useEntityId(props);

  const [assessment, setAssessment] = useState<CarbonAssessment | null>(null);
  const [tierInfo, setTierInfo] = useState<TierInfo | null>(null);
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
      const [assess, info] = await Promise.all([
        fetchAssessment(entityId).catch(() => null),
        fetchTierInfo(entityId).catch(() => null),
      ]);
      if (assess) setAssessment(assess);
      if (info) setTierInfo(info);
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
      const mgmt = getManagementData();
      const result = await triggerCalculation(entityId, {
        management: mgmt || undefined,
      });
      setAssessment(result);
      const info = await fetchTierInfo(entityId);
      if (info) setTierInfo(info);
    } catch (err) {
      setError(t('error_loading'));
    } finally {
      setCalculating(false);
    }
  }, [entityId, t]);

  // Loading state
  if (loading) {
    return (
      <div style={{ padding: '16px', display: 'flex', justifyContent: 'center' }}>
        <Spinner size="sm" />
      </div>
    );
  }

  // Error state
  if (error && !assessment) {
    return (
      <div style={{ padding: '16px' }}>
        <EmptyState
          title={t('error_loading')}
          description={error}
          action={<Button onClick={loadData} variant="secondary" size="sm">{t('retry')}</Button>}
        />
      </div>
    );
  }

  // Empty state
  if (!assessment) {
    return (
      <div style={{ padding: '16px' }}>
        <EmptyState
          title={t('title')}
          description={t('no_data')}
          action={
            <Button onClick={handleCalculate} loading={calculating} variant="primary" size="md">
              {calculating ? t('calculating') : t('calculate')}
            </Button>
          }
        />
      </div>
    );
  }

  const gaps = tierInfo?.gaps || [];
  const confidence = assessment.confidence;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        padding: '12px',
        maxWidth: '320px',
        minWidth: 0,
        boxSizing: 'border-box',
      }}
    >
      {/* Header + Tier Badge */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
          flexWrap: 'wrap',
        }}
      >
        <h3
          style={{
            margin: 0,
            fontSize: '16px',
            fontWeight: 600,
            color: '#111827',
          }}
        >
          {t('title')}
        </h3>
        <CarbonTierBadge tier={assessment.tier} confidence={confidence} compact />
      </div>

      {/* Last assessment date */}
      {assessment.assessment_date && (
        <div style={{ fontSize: '11px', color: '#9CA3AF' }}>
          {t('calculated_at')}:{' '}
          {new Date(assessment.assessment_date).toLocaleDateString()}
        </div>
      )}

      {/* Key Metrics */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '8px',
        }}
      >
        <CompactKPI
          label={t('co2SequesteredCumulative')}
          value={assessment.co2_sequestered_cumulative.value.toFixed(1)}
          unit={assessment.co2_sequestered_cumulative.unit}
        />
        <CompactKPI
          label={t('carbonStockTotal')}
          value={assessment.carbon_stock_total?.value.toFixed(1) ?? '--'}
          unit={assessment.carbon_stock_total?.unit ?? t('units.tC_ha')}
        />
        <CompactKPI
          label={t('soilCarbonDelta')}
          value={
            assessment.soil_carbon_delta
              ? `${assessment.soil_carbon_delta.value > 0 ? '+' : ''}${assessment.soil_carbon_delta.value.toFixed(2)}`
              : '--'
          }
          unit={assessment.soil_carbon_delta?.unit ?? t('units.tC_ha_yr')}
        />
        <CompactKPI
          label={t('gppDaily')}
          value={assessment.gpp_daily.value.toFixed(2)}
          unit={assessment.gpp_daily.unit}
        />
      </div>

      {/* Gaps (top 2) */}
      {gaps.length > 0 && (
        <div>
          <div
            style={{
              fontSize: '11px',
              fontWeight: 600,
              color: '#6B7280',
              textTransform: 'uppercase',
              marginBottom: '6px',
            }}
          >
            {t('gaps')}
          </div>
          <CarbonGapList
            gaps={gaps}
            missingForNextTier={assessment.missing_for_next_tier}
            maxItems={2}
          />
        </div>
      )}

      {/* Calculate button */}
      <Button
        onClick={handleCalculate}
        loading={calculating}
        variant="primary"
        size="md"
        style={{ width: '100%' }}
      >
        {calculating ? t('calculating') : t('calculate')}
      </Button>
    </div>
  );
};

function CompactKPI({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit: string;
}) {
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
          fontSize: '15px',
          fontWeight: 600,
          color: '#111827',
          lineHeight: 1.2,
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontSize: '10px',
          color: '#9CA3AF',
        }}
      >
        {unit}
      </div>
    </div>
  );
}

export default CarbonContextPanel;
