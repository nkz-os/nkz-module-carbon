import React, { useState, useCallback, useMemo } from 'react';
import { useTranslation } from '@nekazari/sdk';
import { Select } from '@nekazari/ui-kit';
import { fetchMRVReport, downloadMRVReport } from '../api/carbonApi';
import type { MRVReport } from '../api/carbonApi';
import { colors } from './styles';
import { fmt, fmtSigned } from './campaignFormat';

interface CarbonMRVExportProps {
  entityId: string;
  years: number[];
}

const STANDARD_LABELS: Record<string, string> = {
  VM0042: 'export_vm0042',
  GOLD_STANDARD_SOC: 'export_gold_standard',
};

const CarbonMRVExport: React.FC<CarbonMRVExportProps> = ({ entityId, years }) => {
  const { t } = useTranslation('carbon');
  const sorted = useMemo(() => [...years].sort((a, b) => a - b), [years]);
  const [fromYear, setFromYear] = useState<number | undefined>(sorted[sorted.length - 1]);
  const [toYear, setToYear] = useState<number | undefined>(sorted[sorted.length - 1]);
  const [loadingStandard, setLoadingStandard] = useState<string | null>(null);
  const [report, setReport] = useState<MRVReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const yearOptions = sorted.map((y) => ({ value: String(y), label: String(y) }));

  const handleExport = useCallback(
    async (standard: string) => {
      setLoadingStandard(standard);
      setError(null);
      try {
        const data = await fetchMRVReport(entityId, standard, fromYear, toYear);
        setReport(data);
        downloadMRVReport(entityId, data);
      } catch (err) {
        setError(err instanceof Error ? err.message : t('error_loading'));
      } finally {
        setLoadingStandard(null);
      }
    },
    [entityId, fromYear, toYear, t],
  );

  if (sorted.length === 0) {
    return <div style={{ fontSize: '13px', color: colors.textSecondary }}>{t('no_data')}</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ padding: '10px 14px', backgroundColor: colors.bgMuted, borderRadius: '6px',
        border: `1px solid ${colors.border}`, fontSize: '13px', color: colors.textPrimary }}>
        {t('not_certified')}
      </div>

      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '12px', color: colors.textSecondary }}>{t('from_campaign')}</span>
        <div style={{ width: '110px' }}>
          <Select value={String(fromYear ?? '')} onValueChange={(v: string) => setFromYear(Number(v))} options={yearOptions} size="sm" />
        </div>
        <span style={{ fontSize: '12px', color: colors.textSecondary }}>{t('to_campaign')}</span>
        <div style={{ width: '110px' }}>
          <Select value={String(toYear ?? '')} onValueChange={(v: string) => setToYear(Number(v))} options={yearOptions} size="sm" />
        </div>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
        {Object.entries(STANDARD_LABELS).map(([standard, labelKey]) => (
          <button
            key={standard}
            onClick={() => handleExport(standard)}
            disabled={loadingStandard === standard}
            style={{
              padding: '10px 16px',
              border: `1px solid ${colors.gray300}`,
              borderRadius: '8px',
              backgroundColor: loadingStandard === standard ? colors.bgMuted : colors.bgSurface,
              color: colors.textPrimary,
              fontSize: '13px',
              fontWeight: 500,
              cursor: loadingStandard === standard ? 'not-allowed' : 'pointer',
            }}
          >
            {loadingStandard === standard ? t('loading') : t(labelKey)}
          </button>
        ))}
      </div>

      {error && (
        <div style={{ padding: '10px 14px', backgroundColor: '#FEF2F2', border: '1px solid #FECACA', borderRadius: '6px',
          color: colors.danger, fontSize: '13px' }}>
          {error}
        </div>
      )}

      {report && (
        <div style={{ padding: '12px 16px', backgroundColor: colors.bgSubtle, borderRadius: '8px',
          border: `1px solid ${colors.border}`, display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ fontSize: '13px', fontWeight: 600, color: colors.textPrimary }}>
            {report.standard_structure} · {report.reporting_period_start} → {report.reporting_period_end}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px' }}>
            <MetricItem label={t('soilCarbonDelta')} value={`${fmtSigned(report.total_delta_soc_tC_ha)} ${t('units.tC_ha')}`} />
            <MetricItem label={t('co2eq_net')} value={`${fmtSigned(report.total_co2eq_net_tCO2eq_ha)} ${t('units.tCO2eq_ha')}`} />
            <MetricItem
              label={t('net_reductions')}
              value={report.net_emission_reductions_tCO2eq_ha !== null
                ? `${fmt(report.net_emission_reductions_tCO2eq_ha)} ${t('units.tCO2eq_ha')}`
                : report.baseline_reference_year === null
                  ? t('baseline_missing')
                  : t('baseline_incomplete', { years: (report.baseline_incomplete_years ?? []).join(', ') })}
            />
            <MetricItem label={t('tier')} value={`T${report.tier}`} />
          </div>
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: colors.textSecondary, textTransform: 'uppercase',
              marginBottom: '6px' }}>
              {t('certification_gaps')}
            </div>
            <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '12px', color: colors.textSecondary }}>
              {report.certification_gaps.map((g) => <li key={g}>{t(`gap.${g}`, { defaultValue: g })}</li>)}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
};

function MetricItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: '11px', color: colors.textMuted, marginBottom: '2px' }}>{label}</div>
      <div style={{ fontSize: '14px', fontWeight: 600, color: colors.textPrimary }}>{value}</div>
    </div>
  );
}

export default CarbonMRVExport;
