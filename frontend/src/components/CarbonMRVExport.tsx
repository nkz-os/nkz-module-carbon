import React, { useState, useCallback } from 'react';
import { useTranslation } from '@nekazari/sdk';
import { fetchMRVReport, downloadMRVReport } from '../api/carbonApi';
import type { MRVReport } from '../api/carbonApi';

interface CarbonMRVExportProps {
  entityId: string;
}

const STANDARD_LABELS: Record<string, string> = {
  VM0042: 'export_vm0042',
  'gold-standard': 'export_gold_standard',
};

const CarbonMRVExport: React.FC<CarbonMRVExportProps> = ({ entityId }) => {
  const { t } = useTranslation('carbon');
  const [loadingStandard, setLoadingStandard] = useState<string | null>(null);
  const [report, setReport] = useState<MRVReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExport = useCallback(
    async (standard: string) => {
      setLoadingStandard(standard);
      setError(null);
      try {
        const data = await fetchMRVReport(entityId, standard);
        setReport(data);
        await downloadMRVReport(entityId, standard);
      } catch (err) {
        setError(err instanceof Error ? err.message : t('error_loading'));
      } finally {
        setLoadingStandard(null);
      }
    },
    [entityId, t],
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Export buttons */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '8px',
        }}
      >
        {Object.entries(STANDARD_LABELS).map(([standard, labelKey]) => (
          <button
            key={standard}
            onClick={() => handleExport(standard)}
            disabled={loadingStandard === standard}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '10px 16px',
              border: '1px solid #D1D5DB',
              borderRadius: '8px',
              backgroundColor: loadingStandard === standard ? '#F3F4F6' : '#FFFFFF',
              color: '#374151',
              fontSize: '13px',
              fontWeight: 500,
              cursor: loadingStandard === standard ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s ease',
              opacity: loadingStandard === standard ? 0.7 : 1,
            }}
            onMouseEnter={(e) => {
              if (loadingStandard !== standard) {
                e.currentTarget.style.backgroundColor = '#F9FAFB';
                e.currentTarget.style.borderColor = '#9CA3AF';
              }
            }}
            onMouseLeave={(e) => {
              if (loadingStandard !== standard) {
                e.currentTarget.style.backgroundColor = '#FFFFFF';
                e.currentTarget.style.borderColor = '#D1D5DB';
              }
            }}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M3 11V13H13V11M8 10V3M8 3L5 6M8 3L11 6"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            {loadingStandard === standard ? t('loading') : t(labelKey)}
          </button>
        ))}
      </div>

      {/* Error state */}
      {error && (
        <div
          style={{
            padding: '10px 14px',
            backgroundColor: '#FEF2F2',
            border: '1px solid #FECACA',
            borderRadius: '6px',
            color: '#991B1B',
            fontSize: '13px',
          }}
        >
          {error}
        </div>
      )}

      {/* Report summary */}
      {report && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#F9FAFB',
            borderRadius: '8px',
            border: '1px solid #E5E7EB',
          }}
        >
          <div
            style={{
              fontSize: '13px',
              fontWeight: 600,
              color: '#374151',
              marginBottom: '12px',
            }}
          >
            {report.standard} - {new Date(report.generated_at).toLocaleString()}
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
              gap: '12px',
            }}
          >
            <MetricItem label="Net Reductions" value={`${report.net_emission_reductions.toFixed(2)} tCO2e`} />
            <MetricItem label="Verified Credits" value={`${report.verified_credits.toFixed(2)}`} />
            <MetricItem label="Buffer Pool" value={`${report.buffer_pool.toFixed(2)} %`} />
            <MetricItem label="Leakage" value={`${report.leakage.toFixed(2)} %`} />
            <MetricItem label="Uncertainty" value={`${report.uncertainty_deduction.toFixed(2)} %`} />
          </div>
        </div>
      )}
    </div>
  );
};

function MetricItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: '11px', color: '#9CA3AF', marginBottom: '2px' }}>{label}</div>
      <div style={{ fontSize: '14px', fontWeight: 600, color: '#374151' }}>{value}</div>
    </div>
  );
}

export default CarbonMRVExport;
