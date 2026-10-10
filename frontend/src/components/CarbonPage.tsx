import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from '@nekazari/sdk';
import { Select, DataTable, MetricCard, MetricGrid, EmptyState, Spinner, Panel } from '@nekazari/ui-kit';
import { useSearchParams } from 'react-router-dom';
import CarbonBottomPanel from './CarbonBottomPanel';
import CarbonTierBadge from './CarbonTierBadge';
import { fetchTenantSummary } from '../api/carbonApi';
import { colors } from './styles';
import type { ParcelSummary, YearlyAggregation } from '../api/carbonApi';
import { DASH, currentYear, fmt, fmtSigned } from './campaignFormat';

interface SummaryRow extends ParcelSummary {
  id: string;
}

const CarbonPage: React.FC = () => {
  const { t } = useTranslation('carbon');
  const [searchParams, setSearchParams] = useSearchParams();
  const entityId = searchParams.get('entityId') || '';

  const [summary, setSummary] = useState<SummaryRow[]>([]);
  const [yearlyData, setYearlyData] = useState<YearlyAggregation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedYear, setSelectedYear] = useState<string>(String(currentYear()));

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTenantSummary(Number(selectedYear));
      setSummary(data.parcels.map((p) => ({ ...p, id: p.parcel_id })));
      setYearlyData(data.yearly_aggregations);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('error_loading'));
    } finally {
      setLoading(false);
    }
  }, [selectedYear, t]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const handleParcelSelect = useCallback(
    (parcelId: string) => {
      setSearchParams(parcelId ? { entityId: parcelId } : {});
    },
    [setSearchParams],
  );

  const yearOptions = Array.from(new Set([currentYear(), ...yearlyData.map((y) => y.year)]))
    .sort((a, b) => b - a)
    .map((y) => ({ value: String(y), label: String(y) }));

  // Metric cards: means over the parcels whose campaign is computed (absent values excluded)
  const selectedAgg = yearlyData.find((y) => String(y.year) === selectedYear);
  const computedCount = summary.filter((p) => p.campaign_year !== null).length;

  const columns = [
    {
      accessorKey: 'parcel_name' as const,
      header: t('parcel_name'),
      cell: (info: { getValue: () => string; row: { original: SummaryRow } }) => (
        <button
          onClick={() => handleParcelSelect(info.row.original.parcel_id)}
          style={{
            background: 'none',
            border: 'none',
            color: colors.accentBase,
            cursor: 'pointer',
            fontWeight: 500,
            fontSize: '13px',
            textAlign: 'left',
            padding: 0,
          }}
        >
          {info.getValue() || info.row.original.parcel_id}
        </button>
      ),
    },
    {
      accessorKey: 'crop_species' as const,
      header: t('crop_species'),
    },
    {
      accessorKey: 'co2_gross_tCO2_ha' as const,
      header: t('co2_gross'),
      cell: (info: { getValue: () => number | null }) => `${fmt(info.getValue(), 1)} ${t('units.tCO2_ha')}`,
    },
    {
      accessorKey: 'delta_soc_tC_ha' as const,
      header: t('soilCarbonDelta'),
      cell: (info: { getValue: () => number | null }) => `${fmtSigned(info.getValue())} ${t('units.tC_ha')}`,
    },
    {
      accessorKey: 'co2eq_net_tCO2eq_ha' as const,
      header: t('co2eq_net'),
      cell: (info: { getValue: () => number | null }) => `${fmtSigned(info.getValue(), 1)} ${t('units.tCO2eq_ha')}`,
    },
    {
      accessorKey: 'tier' as const,
      header: t('tier'),
      cell: (info: { getValue: () => number }) => <CarbonTierBadge tier={info.getValue()} compact />,
    },
    {
      accessorKey: 'computed_through' as const,
      header: t('computed_through'),
      cell: (info: { getValue: () => string | null }) => info.getValue() ?? DASH,
    },
  ];

  const yearlyColumns = [
    { accessorKey: 'year' as const, header: t('year') },
    {
      accessorKey: 'co2_gross_tCO2_ha_mean' as const,
      header: t('co2_gross_mean'),
      cell: (info: { getValue: () => number | null }) => `${fmt(info.getValue(), 1)} ${t('units.tCO2_ha')}`,
    },
    {
      accessorKey: 'delta_soc_tC_ha_mean' as const,
      header: t('delta_soc_mean'),
      cell: (info: { getValue: () => number | null }) => `${fmtSigned(info.getValue())} ${t('units.tC_ha')}`,
    },
    { accessorKey: 'parcel_count' as const, header: t('parcel_count') },
  ];

  // Loading
  if (loading) {
    return (
      <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '24px 16px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: colors.textPrimary, marginBottom: '8px' }}>{t('title')}</h1>
        <div style={{ display: 'flex', justifyContent: 'center', padding: '80px 0' }}>
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  // Error
  if (error && summary.length === 0) {
    return (
      <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '24px 16px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: colors.textPrimary, marginBottom: '8px' }}>{t('title')}</h1>
        <EmptyState
          title={t('error_loading')}
          description={error}
          action={<button onClick={loadSummary} className="nkz-btn nkz-btn-secondary">{t('retry')}</button>}
        />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '24px 16px', minHeight: '100vh' }}>
      <h1 style={{ fontSize: '24px', fontWeight: 700, color: colors.textPrimary, marginBottom: '8px' }}>
        {t('summary_title')}
      </h1>
      <p style={{ fontSize: '14px', color: colors.textSecondary, marginBottom: '24px' }}>
        {t('tier_description')}
      </p>

      {/* Parcel selector */}
      <div style={{ marginBottom: '24px', maxWidth: '400px' }}>
        <Panel>
          <Panel.Body>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <label style={{ fontSize: '13px', fontWeight: 600, color: colors.textPrimary }}>
                {t('select_parcel')}
              </label>
              <Select
                value={entityId}
                onValueChange={handleParcelSelect}
                options={[
                  { value: '', label: t('select_parcel') },
                  ...summary.map((p) => ({
                    value: p.parcel_id,
                    label: `${p.parcel_name}${p.crop_species ? ` (${p.crop_species})` : ''}`,
                  })),
                ]}
                size="sm"
              />
            </div>
          </Panel.Body>
        </Panel>
      </div>

      {/* Parcel detail */}
      {entityId && (
        <div style={{ marginBottom: '32px' }}>
          <CarbonBottomPanel entityId={entityId} />
        </div>
      )}

      {/* KPIs */}
      <MetricGrid columns={3}>
        <MetricCard
          label={t('co2_gross_mean')}
          value={fmt(selectedAgg?.co2_gross_tCO2_ha_mean, 1)}
          unit={t('units.tCO2_ha')}
        />
        <MetricCard
          label={t('delta_soc_mean')}
          value={fmtSigned(selectedAgg?.delta_soc_tC_ha_mean)}
          unit={t('units.tC_ha')}
        />
        <MetricCard
          label={t('parcels_computed')}
          value={`${computedCount} / ${summary.length}`}
        />
      </MetricGrid>

      {/* Year filter */}
      <div style={{ marginTop: '24px', marginBottom: '16px', maxWidth: '200px' }}>
        <Select
          value={selectedYear}
          onValueChange={setSelectedYear}
          options={yearOptions}
          size="sm"
        />
      </div>

      {/* Parcel summary table */}
      <div style={{ marginBottom: '32px' }}>
        <DataTable
          columns={columns}
          data={summary}
          density="compact"
          emptyState={
            <EmptyState
              title={t('no_data')}
              description={t('no_data')}
            />
          }
        />
      </div>

      {/* Yearly aggregation table */}
      {yearlyData.length > 0 && (
        <div style={{ marginBottom: '32px' }}>
          <h2 style={{ fontSize: '18px', fontWeight: 600, color: colors.textPrimary, marginBottom: '12px' }}>
            {t('yearly_aggregation')}
          </h2>
          <DataTable
            columns={yearlyColumns}
            data={yearlyData}
            density="compact"
          />
        </div>
      )}
    </div>
  );
};

export default CarbonPage;
