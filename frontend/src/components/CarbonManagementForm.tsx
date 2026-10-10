import React, { useState, useCallback, useEffect } from 'react';
import { useTranslation } from '@nekazari/sdk';
import { Select } from '@nekazari/ui-kit';
import { saveManagement, fetchAvailableSensors, fetchManagement } from '../api/carbonApi';
import type { ManagementData, SensorInfo } from '../api/carbonApi';
import { colors } from './styles';

interface CarbonManagementFormProps {
  entityId: string;
  onSaved?: () => void;
}

/** Raw form values: '' means "not declared" and is never sent. */
type Draft = Record<string, string>;

const NUMBER_FIELDS: Array<{ key: keyof ManagementData; labelKey: string; scale?: number; min: number; max?: number; step: number }> = [
  { key: 'harvest_export_fraction', labelKey: 'harvest_export_pct', scale: 100, min: 0, max: 100, step: 1 },
  { key: 'residue_removal_fraction', labelKey: 'residue_removal_pct', scale: 100, min: 0, max: 100, step: 1 },
  { key: 'organic_amendments_tC_ha_yr', labelKey: 'organic_amendments', min: 0, step: 0.1 },
  { key: 'n_synthetic_kgN_ha_yr', labelKey: 'n_synthetic', min: 0, step: 1 },
  { key: 'n_organic_kgN_ha_yr', labelKey: 'n_organic', min: 0, step: 1 },
  { key: 'soil_lab_soc_tC_ha', labelKey: 'soil_lab_soc', min: 0, step: 0.1 },
  { key: 'soil_lab_clay_pct', labelKey: 'soil_lab_clay', min: 0, max: 100, step: 0.1 },
  { key: 'cover_crop_months', labelKey: 'cover_crop_months', min: 0, max: 12, step: 1 },
];

const TILLAGE_OPTIONS = [
  { value: 'conventional', labelKey: 'tillage_conventional' },
  { value: 'reduced', labelKey: 'tillage_reduced' },
  { value: 'no_till', labelKey: 'tillage_no_till' },
];

const WEATHER_SOURCE_OPTIONS = [
  { value: 'weather_worker', labelKey: 'weather_worker' },
  { value: 'sensor', labelKey: 'weather_sensor' },
];

function toDraft(data: ManagementData): Draft {
  const d: Draft = {};
  for (const f of NUMBER_FIELDS) {
    const v = data[f.key] as number | null | undefined;
    d[f.key] = v === null || v === undefined ? '' : String(f.scale ? Math.round(v * f.scale * 100) / 100 : v);
  }
  d.tillage_type = data.tillage_type ?? '';
  d.irrigated = data.irrigated === undefined || data.irrigated === null ? '' : data.irrigated ? 'yes' : 'no';
  d.residues_removed = data.residues_removed === undefined || data.residues_removed === null ? '' : data.residues_removed ? 'yes' : 'no';
  d.weather_source = data.weather_source ?? '';
  d.weather_sensor_id = data.weather_sensor_id ?? '';
  return d;
}

function fromDraft(d: Draft): ManagementData {
  const out: ManagementData = {};
  for (const f of NUMBER_FIELDS) {
    const raw = (d[f.key] ?? '').trim();
    if (raw === '') continue;
    const n = Number(raw);
    if (Number.isNaN(n)) continue;
    (out as Record<string, number>)[f.key] = f.scale ? n / f.scale : n;
  }
  if (d.tillage_type) out.tillage_type = d.tillage_type;
  if (d.irrigated) out.irrigated = d.irrigated === 'yes';
  if (d.residues_removed) out.residues_removed = d.residues_removed === 'yes';
  if (d.weather_source) out.weather_source = d.weather_source;
  if (d.weather_source === 'sensor' && d.weather_sensor_id) out.weather_sensor_id = d.weather_sensor_id;
  return out;
}

const CarbonManagementForm: React.FC<CarbonManagementFormProps> = ({ entityId, onSaved }) => {
  const { t } = useTranslation('carbon');
  const [draft, setDraft] = useState<Draft>(() => toDraft({}));
  const [sensors, setSensors] = useState<SensorInfo[]>([]);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Start from what is stored: saving must never re-declare values the farmer did not enter.
  useEffect(() => {
    if (!entityId) return;
    fetchManagement(entityId).then((m) => setDraft(toDraft(m))).catch(() => setDraft(toDraft({})));
  }, [entityId]);

  useEffect(() => {
    if (draft.weather_source === 'sensor' && entityId) {
      fetchAvailableSensors(entityId).then(setSensors).catch(() => setSensors([]));
    }
  }, [draft.weather_source, entityId]);

  const set = (key: string, value: string) => setDraft((d) => ({ ...d, [key]: value }));

  const handleSave = useCallback(async () => {
    setSaveState('saving');
    setErrorMsg(null);
    try {
      await saveManagement(entityId, fromDraft(draft));
      setSaveState('saved');
      onSaved?.();
      setTimeout(() => setSaveState('idle'), 2000);
    } catch (err) {
      setSaveState('error');
      setErrorMsg(err instanceof Error ? err.message : t('error'));
    }
  }, [entityId, draft, onSaved, t]);

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 10px',
    border: `1px solid ${colors.gray300}`,
    borderRadius: '6px',
    fontSize: '13px',
    color: colors.textPrimary,
    backgroundColor: colors.bgSurface,
    boxSizing: 'border-box',
  };
  const labelStyle: React.CSSProperties = { fontSize: '12px', fontWeight: 500, color: colors.textSecondary, marginBottom: '4px' };
  const rowStyle: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: '4px' };
  const triState = [
    { value: '', label: t('not_declared') },
    { value: 'yes', label: t('yes') },
    { value: 'no', label: t('no') },
  ];

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        handleSave();
      }}
      style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}
    >
      <div style={{ fontSize: '12px', color: colors.textSecondary }}>{t('declare_hint')}</div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '12px' }}>
        {NUMBER_FIELDS.map((f) => (
          <div key={f.key} style={rowStyle}>
            <label style={labelStyle}>{t(f.labelKey)}</label>
            <input
              type="number"
              min={f.min}
              max={f.max}
              step={f.step}
              value={draft[f.key] ?? ''}
              placeholder={t('not_declared')}
              onChange={(e) => set(f.key, e.target.value)}
              style={inputStyle}
            />
          </div>
        ))}

        <div style={rowStyle}>
          <label style={labelStyle}>{t('irrigated')}</label>
          <Select value={draft.irrigated} onValueChange={(v: string) => set('irrigated', v)} options={triState} size="sm" />
        </div>

        <div style={rowStyle}>
          <label style={labelStyle}>{t('residues_removed')}</label>
          <Select value={draft.residues_removed} onValueChange={(v: string) => set('residues_removed', v)} options={triState} size="sm" />
        </div>

        <div style={rowStyle}>
          <label style={labelStyle}>{t('tillage')}</label>
          <Select
            value={draft.tillage_type}
            onValueChange={(v: string) => set('tillage_type', v)}
            options={[{ value: '', label: t('not_declared') }, ...TILLAGE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))]}
            size="sm"
          />
        </div>

        <div style={rowStyle}>
          <label style={labelStyle}>{t('weather_source')}</label>
          <Select
            value={draft.weather_source}
            onValueChange={(v: string) => set('weather_source', v)}
            options={[{ value: '', label: t('not_declared') }, ...WEATHER_SOURCE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))]}
            size="sm"
          />
        </div>

        {draft.weather_source === 'sensor' && (
          <div style={rowStyle}>
            <label style={labelStyle}>{t('select_sensor')}</label>
            <Select
              value={draft.weather_sensor_id}
              onValueChange={(v: string) => set('weather_sensor_id', v)}
              options={[
                { value: '', label: t('select_sensor') },
                ...sensors.map((s) => ({ value: s.id, label: `${s.name}${s.sensor_type ? ` (${s.sensor_type})` : ''}` })),
              ]}
              size="sm"
            />
          </div>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          type="submit"
          disabled={saveState === 'saving'}
          style={{
            padding: '8px 20px',
            border: 'none',
            borderRadius: '6px',
            backgroundColor: saveState === 'saving' ? colors.gray300 : colors.accentBase,
            color: '#FFFFFF',
            fontSize: '13px',
            fontWeight: 500,
            cursor: saveState === 'saving' ? 'not-allowed' : 'pointer',
          }}
        >
          {saveState === 'saved' ? t('saved') : saveState === 'saving' ? t('saving') : t('save')}
        </button>
        {saveState === 'error' && errorMsg && (
          <span style={{ fontSize: '12px', color: colors.danger }}>{errorMsg}</span>
        )}
      </div>
    </form>
  );
};

export default CarbonManagementForm;
