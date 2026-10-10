import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation, useViewerOptional } from '@nekazari/sdk';
import { useParams } from 'react-router-dom';
import { EmptyState, Button, Spinner } from '@nekazari/ui-kit';
import { fetchCampaigns, calculateCampaign } from '../api/carbonApi';
import type { CampaignRow } from '../api/carbonApi';
import CarbonTierBadge from './CarbonTierBadge';
import CarbonMissingList from './CarbonMissingList';
import { colors } from './styles';
import { currentYear, fmt, fmtSigned, shortParcelId } from './campaignFormat';

interface CarbonContextPanelProps {
  entityId?: string;
}

function useEntityId(props: CarbonContextPanelProps): string {
  const viewer = useViewerOptional();
  const params = useParams<{ entityId: string }>();
  // Viewer context is the canonical source when inside the unified viewer
  if (viewer?.selectedEntityId) return shortParcelId(viewer.selectedEntityId);
  return props.entityId || params.entityId || '';
}

const CarbonContextPanel: React.FC<CarbonContextPanelProps> = (props) => {
  const { t } = useTranslation('carbon');
  const entityId = useEntityId(props);
  const year = currentYear();

  const [row, setRow] = useState<CampaignRow | null>(null);
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
      const list = await fetchCampaigns(entityId);
      setRow(list.campaigns.find((c) => c.campaign_label === year) ?? null);
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
    if (!entityId) {
      setError(t('error_no_entity'));
      return;
    }
    setCalculating(true);
    setError(null);
    try {
      setRow(await calculateCampaign(entityId, year));
    } catch {
      setError(t('error_loading'));
    } finally {
      setCalculating(false);
    }
  }, [entityId, year, t]);

  if (loading) {
    return (
      <div style={{ padding: '16px', display: 'flex', justifyContent: 'center' }}>
        <Spinner size="sm" />
      </div>
    );
  }

  if (error && !row) {
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

  if (!row) {
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '12px', maxWidth: '320px',
      minWidth: 0, boxSizing: 'border-box' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: colors.textPrimary }}>
          {t('title')} · {t('campaign')} {row.campaign_label}
        </h3>
        <CarbonTierBadge tier={row.data_tier} compact />
      </div>

      <div style={{ fontSize: '11px', color: colors.textMuted }}>
        {row.computed_through ? `${t('computed_through')}: ${row.computed_through}` : t('campaign_not_computed')}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
        <CompactKPI label={t('co2_gross')} value={fmt(row.co2_sequestered_gross, 1)} unit={t('units.tCO2_ha')} />
        <CompactKPI label={t('soilCarbonDelta')} value={fmtSigned(row.soil_carbon_delta)} unit={t('units.tC_ha')} />
        <CompactKPI label={t('cover_days')} value={String(row.cover_days)} unit={`${t('bare_days')}: ${row.bare_days}`} />
        <CompactKPI label={t('co2eq_net')} value={fmtSigned(row.co2eq_net, 1)} unit={t('units.tCO2eq_ha')} />
      </div>

      <div>
        <div style={{ fontSize: '11px', fontWeight: 600, color: colors.textSecondary, textTransform: 'uppercase',
          marginBottom: '6px' }}>
          {t('missing_title')}
        </div>
        <CarbonMissingList missing={row.missing} maxItems={2} />
      </div>

      <Button onClick={handleCalculate} loading={calculating} variant="primary" size="md" style={{ width: '100%' }}>
        {calculating ? t('calculating') : t('recalculate')}
      </Button>
    </div>
  );
};

function CompactKPI({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div style={{ padding: '8px', backgroundColor: colors.bgSubtle, borderRadius: '6px',
      border: `1px solid ${colors.border}`, minWidth: 0 }}>
      <div style={{ fontSize: '10px', color: colors.textMuted, marginBottom: '2px', whiteSpace: 'nowrap',
        overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {label}
      </div>
      <div style={{ fontSize: '15px', fontWeight: 600, color: colors.textPrimary, lineHeight: 1.2 }}>{value}</div>
      <div style={{ fontSize: '10px', color: colors.textMuted }}>{unit}</div>
    </div>
  );
}

export default CarbonContextPanel;
