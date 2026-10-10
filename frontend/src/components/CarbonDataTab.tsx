import React from 'react';
import { useTranslation } from '@nekazari/sdk';
import type { CampaignRow, OperationUsed } from '../api/carbonApi';
import { colors } from './styles';
import { DASH, fmt } from './campaignFormat';

interface CarbonDataTabProps {
  row: CampaignRow | null;
}

const cell: React.CSSProperties = { padding: '4px 8px', fontSize: '12px', color: colors.textPrimary, whiteSpace: 'nowrap' };
const head: React.CSSProperties = { ...cell, color: colors.textSecondary, fontWeight: 600, textAlign: 'left' };

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: '11px', fontWeight: 600, color: colors.textSecondary, textTransform: 'uppercase',
        letterSpacing: '0.5px', marginBottom: '8px' }}>
        {title}
      </div>
      {children}
    </div>
  );
}

/** What entered this campaign's balance and where each input came from. */
const CarbonDataTab: React.FC<CarbonDataTabProps> = ({ row }) => {
  const { t } = useTranslation('carbon');
  const s = row?.inputs_summary;
  if (!row || !s) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 20px', color: colors.textMuted, fontSize: '14px' }}>
        {t('no_data')}
      </div>
    );
  }

  const opDetail = (o: OperationUsed): string => {
    switch (o.type) {
      case 'harvest':
        return o.exported_c_tC_ha === null || o.exported_c_tC_ha === undefined
          ? t('data.export_unknown')
          : `${t('exported')}: ${fmt(o.exported_c_tC_ha)} ${t('units.tC_ha')}`;
      case 'fertilization':
        return `${o.organic ? t('data.organic') : t('data.mineral')} · N ${fmt(o.n_kg_ha, 0)} kg/ha`;
      case 'tillage':
        return o.tillage_type ? t(`data.tillage.${o.tillage_type}`, { defaultValue: o.tillage_type }) : DASH;
      case 'irrigation':
        return o.water_m3_ha === null || o.water_m3_ha === undefined ? DASH : `${fmt(o.water_m3_ha, 0)} m³/ha`;
      default:
        return '';
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <Section title={t('data.weather')}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
          {Object.entries(s.weather_days_by_source).map(([src, n]) => (
            <span key={src} style={{ padding: '2px 8px', backgroundColor: colors.bgMuted, borderRadius: '4px',
              fontSize: '11px', color: colors.textSecondary }}>
              {t(`data.source.${src}`, { defaultValue: src })}: {n} {t('data.days')}
            </span>
          ))}
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead>
              <tr>
                {['data.month', 'data.temp', 'data.rain', 'data.et0', 'cover_days', 'data.plant_c', 'data.fym_c', 'data.co2_c']
                  .map((k) => <th key={k} style={head}>{t(k)}</th>)}
              </tr>
            </thead>
            <tbody>
              {row.monthly_balance.map((m) => (
                <tr key={m.month} style={{ borderTop: `1px solid ${colors.border}` }}>
                  <td style={cell}>{m.month}</td>
                  <td style={cell}>{fmt(m.temp_c, 1)}</td>
                  <td style={cell}>{fmt(m.rain_mm, 1)}</td>
                  <td style={cell}>{fmt(m.et0_mm, 1)}</td>
                  <td style={cell}>{m.cover_days}</td>
                  <td style={cell}>{fmt(m.plant_c_tC_ha, 3)}</td>
                  <td style={cell}>{fmt(m.fym_c_tC_ha, 3)}</td>
                  <td style={cell}>{fmt(m.co2_c_tC_ha, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title={t('data.vegetation')}>
        {Object.keys(s.vi).length === 0 ? (
          <div style={{ fontSize: '12px', color: colors.textSecondary }}>{t('data.no_scenes')}</div>
        ) : (
          Object.entries(s.vi).map(([idx, v]) => v && (
            <div key={idx} style={{ fontSize: '12px', color: colors.textPrimary }}>
              {idx}: {t('data.scenes', { n: v.scenes })} · {v.first} → {v.last}
              {v.max_gap_days !== null && ` · ${t('data.max_gap', { n: v.max_gap_days })}`}
            </div>
          ))
        )}
      </Section>

      <Section title={t('data.soil')}>
        {s.soil ? (
          <div style={{ fontSize: '12px', color: colors.textPrimary }}>
            {t(`data.source.${s.soil.source}`, { defaultValue: s.soil.source })} · SOC {fmt(s.soil.soc_tC_ha, 1)} {t('units.tC_ha')} ·{' '}
            {t('data.clay')} {fmt(s.soil.clay_pct, 1)} % · 0–{fmt(s.soil.depth_cm, 0)} cm
          </div>
        ) : (
          <div style={{ fontSize: '12px', color: colors.textSecondary }}>{t('missing.soil')}</div>
        )}
      </Section>

      <Section title={t('data.operations')}>
        {s.operations.length === 0 ? (
          <div style={{ fontSize: '12px', color: colors.textSecondary }}>{t('data.no_operations')}</div>
        ) : (
          <table style={{ borderCollapse: 'collapse' }}>
            <tbody>
              {s.operations.map((o, i) => (
                <tr key={`${o.type}-${o.date}-${i}`}>
                  <td style={cell}>{o.date}</td>
                  <td style={cell}>{t(`data.op.${o.type}`)}</td>
                  <td style={cell}>{opDetail(o)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {s.irrigated && (
          <div style={{ fontSize: '12px', color: colors.textSecondary, marginTop: '6px' }}>
            {t('irrigated')}: {s.irrigated.value ? t('yes') : t('no')}
            {s.irrigated.source && ` (${t(`data.from_${s.irrigated.source}`)})`}
          </div>
        )}
      </Section>

      <Section title={t('cycles')}>
        {row.cycle_breakdown.length === 0 ? (
          <div style={{ fontSize: '12px', color: colors.textSecondary }}>{t('missing.cycles')}</div>
        ) : (
          row.cycle_breakdown.map((c) => (
            <div key={c.crop_id} style={{ fontSize: '12px', color: colors.textPrimary }}>
              {c.species} · {c.start} ({t(`data.prov.${c.start_provenance}`, { defaultValue: c.start_provenance })}) →{' '}
              {c.end ?? DASH}
              {c.end_provenance && ` (${t(`data.prov.${c.end_provenance}`, { defaultValue: c.end_provenance })})`}
            </div>
          ))
        )}
      </Section>
    </div>
  );
};

export default CarbonDataTab;
