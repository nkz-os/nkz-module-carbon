import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from '@nekazari/sdk';
import { Select, DataTable, MetricCard, MetricGrid, EmptyState, Spinner, Panel } from '@nekazari/ui-kit';
import { useSearchParams } from 'react-router-dom';
import CarbonBottomPanel from './CarbonBottomPanel';
import CarbonTierBadge from './CarbonTierBadge';
import { fetchTenantSummary } from '../api/carbonApi';
import type { ParcelSummary, YearlyAggregation } from '../api/carbonApi';

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
  const [selectedYear, setSelectedYear] = useState<string>('all');

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const yearParam = selectedYear !== 'all' ? Number(selectedYear) : undefined;
      const data = await fetchTenantSummary(yearParam);
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

  const yearOptions = [
    { value: 'all', label: t('all_years') },
    ...yearlyData.map((y) => ({
      value: String(y.year),
      label: String(y.year),
    })),
  ];

  // Totals for metric cards
  const totalCo2 = summary.reduce((sum, p) => sum + p.co2_captured_cumulative, 0);
  const avgStock = summary.length > 0
    ? summary.reduce((sum, p) => sum + p.carbon_stock_total, 0) / summary.length
    : 0;
  const parcelCount = summary.length;

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
            color: 'var(--nkz-accent-base, #059669)',
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
      accessorKey: 'co2_captured_cumulative' as const,
      header: t('co2_captured'),
      cell: (info: { getValue: () => number }) => `${info.getValue().toFixed(1)} kgCO₂/ha`,
    },
    {
      accessorKey: 'carbon_stock_total' as const,
      header: t('carbon_stock'),
      cell: (info: { getValue: () => number }) => `${info.getValue().toFixed(2)} tC/ha`,
    },
    {
      accessorKey: 'tier' as const,
      header: t('tier'),
      cell: (info: { getValue: () => number; row: { original: SummaryRow } }) => (
        <CarbonTierBadge
          tier={info.getValue()}
          confidence={0}
          compact
        />
      ),
    },
    {
      accessorKey: 'methodology' as const,
      header: t('methodology'),
    },
    {
      accessorKey: 'last_calculation_date' as const,
      header: t('last_calculation'),
    },
  ];

  const yearlyColumns = [
    { accessorKey: 'year' as const, header: t('year') },
    {
      accessorKey: 'total_co2_captured_kg' as const,
      header: t('total_co2_all_parcels'),
      cell: (info: { getValue: () => number }) => `${info.getValue().toFixed(1)} kgCO₂`,
    },
    {
      accessorKey: 'avg_carbon_stock_tC_ha' as const,
      header: t('avg_carbon_stock'),
      cell: (info: { getValue: () => number }) => `${info.getValue().toFixed(2)} tC/ha`,
    },
    { accessorKey: 'parcel_count' as const, header: t('active_parcels') },
  ];

  // Loading
  if (loading) {
    return (
      <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '24px 16px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#111827', marginBottom: '8px' }}>{t('title')}</h1>
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
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#111827', marginBottom: '8px' }}>{t('title')}</h1>
        <EmptyState
          title={t('error_loading')}
          description={error}
          action={{ label: t('retry'), onClick: loadSummary }}
        />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1100px', margin: '0 auto', padding: '24px 16px', minHeight: '100vh' }}>
      <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#111827', marginBottom: '8px' }}>
        {t('summary_title')}
      </h1>
      <p style={{ fontSize: '14px', color: '#6B7280', marginBottom: '24px' }}>
        {t('tier_description')}
      </p>

      {/* Parcel selector */}
      <div style={{ marginBottom: '24px', maxWidth: '400px' }}>
        <Panel>
          <Panel.Body>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151' }}>
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
          label={t('total_co2_all_parcels')}
          value={totalCo2.toFixed(1)}
          unit="kgCO₂/ha"
        />
        <MetricCard
          label={t('avg_carbon_stock')}
          value={avgStock.toFixed(2)}
          unit="tC/ha"
        />
        <MetricCard
          label={t('active_parcels')}
          value={parcelCount}
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
          <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#111827', marginBottom: '12px' }}>
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
