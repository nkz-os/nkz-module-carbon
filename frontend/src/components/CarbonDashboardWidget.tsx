import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation, useViewerOptional } from '@nekazari/sdk';
import { useParams } from 'react-router-dom';
import { MetricCard, MetricGrid, Spinner } from '@nekazari/ui-kit';
import { fetchCampaigns } from '../api/carbonApi';
import type { CampaignRow } from '../api/carbonApi';
import CarbonTierBadge from './CarbonTierBadge';
import { colors } from './styles';
import { currentYear, fmt, fmtSigned, productionUnit, shortParcelId } from './campaignFormat';
import CarbonMissingList from './CarbonMissingList';

interface CarbonDashboardWidgetProps {
  entityId?: string;
}

function useEntityId(props: CarbonDashboardWidgetProps): string {
  const viewer = useViewerOptional();
  const params = useParams<{ entityId: string }>();
  if (viewer?.selectedEntityId) return shortParcelId(viewer.selectedEntityId);
  return props.entityId || params.entityId || '';
}

const CarbonDashboardWidget: React.FC<CarbonDashboardWidgetProps> = (props) => {
  const { t } = useTranslation('carbon');
  const entityId = useEntityId(props);

  const [row, setRow] = useState<CampaignRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!entityId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await fetchCampaigns(entityId);
      setRow(list.campaigns.find((c) => c.campaign_label === currentYear()) ?? null);
    } catch {
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
      <div style={{ padding: '16px', textAlign: 'center', color: colors.danger, fontSize: '13px' }}>{error}</div>
    );
  }

  if (!row) {
    return (
      <div style={{ padding: '16px', textAlign: 'center', color: colors.textSecondary, fontSize: '13px' }}>
        {t('no_data')}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '12px', height: '100%',
      boxSizing: 'border-box', minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
        <span style={{ fontSize: '14px', fontWeight: 600, color: colors.textPrimary }}>
          {t('title')} · {row.campaign_label}
        </span>
        <CarbonTierBadge tier={row.data_tier} compact />
      </div>
      <MetricGrid columns={3}>
        <MetricCard label={t('co2_gross')} value={fmt(row.co2_sequestered_gross, 1)} unit={productionUnit(t('units.tCO2_ha'), row.tier1_coverage, t)} />
        <MetricCard label={t('soilCarbonDelta')} value={fmtSigned(row.soil_carbon_delta)} unit={t('units.tC_ha')} />
        <MetricCard label={t('cover_days')} value={String(row.cover_days)} unit={`${t('bare_days')}: ${row.bare_days}`} />
      </MetricGrid>
      <div style={{ fontSize: '11px', color: colors.textMuted }}>
        {row.computed_through ? `${t('computed_through')}: ${row.computed_through}` : t('campaign_not_computed')}
      </div>
      <CarbonMissingList missing={row.missing} maxItems={2} />
    </div>
  );
};

export default CarbonDashboardWidget;
