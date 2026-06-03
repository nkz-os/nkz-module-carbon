import React, { useState, useCallback, useEffect } from 'react';
import { useTranslation } from '@nekazari/sdk';
import { Select } from '@nekazari/ui-kit';
import { saveManagement, fetchAvailableSensors } from '../api/carbonApi';
import type { ManagementData, SensorInfo } from '../api/carbonApi';

interface CarbonManagementFormProps {
  entityId: string;
  initialData?: Partial<ManagementData>;
  onSaved?: () => void;
}

const TILLAGE_OPTIONS = [
  { value: 'conventional', labelKey: 'tillage_conventional' },
  { value: 'reduced', labelKey: 'tillage_reduced' },
  { value: 'no_till', labelKey: 'tillage_no_till' },
];

const WEATHER_SOURCE_OPTIONS = [
  { value: 'weather_worker', labelKey: 'weather_worker' },
  { value: 'sensor', labelKey: 'weather_sensor' },
];

const CarbonManagementForm: React.FC<CarbonManagementFormProps> = ({
  entityId,
  initialData,
  onSaved,
}) => {
  const { t } = useTranslation('carbon');

  const [tillageType, setTillageType] = useState(initialData?.tillage_type || 'conventional');
  const [residuesRemoved, setResiduesRemoved] = useState(initialData?.residues_removed || false);
  const [coverCropMonths, setCoverCropMonths] = useState(initialData?.cover_crop_months ?? 0);
  const [organicAmendments, setOrganicAmendments] = useState(
    initialData?.organic_amendments_tC_ha_yr ?? 0,
  );
  const [nFertilizerSynthetic, setNFertilizerSynthetic] = useState(
    initialData?.n_synthetic_kgN_ha_yr ?? 0,
  );
  const [nFertilizerOrganic, setNFertilizerOrganic] = useState(
    initialData?.n_organic_kgN_ha_yr ?? 0,
  );
  const [irrigated, setIrrigated] = useState(initialData?.irrigated || false);
  const [weatherSource, setWeatherSource] = useState(initialData?.weather_source || 'weather_worker');
  const [weatherSensorId, setWeatherSensorId] = useState(initialData?.weather_sensor_id || '');
  const [sensors, setSensors] = useState<SensorInfo[]>([]);

  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Fetch available sensors when weather source changes to sensor
  useEffect(() => {
    if (weatherSource === 'sensor' && entityId) {
      fetchAvailableSensors(entityId)
        .then(setSensors)
        .catch(() => setSensors([]));
    }
  }, [weatherSource, entityId]);

  // Sync initial data
  useEffect(() => {
    if (initialData) {
      if (initialData.tillage_type) setTillageType(initialData.tillage_type);
      if (initialData.residues_removed !== undefined) setResiduesRemoved(initialData.residues_removed);
      if (initialData.cover_crop_months !== undefined) setCoverCropMonths(initialData.cover_crop_months);
      if (initialData.organic_amendments_tC_ha_yr !== undefined)
        setOrganicAmendments(initialData.organic_amendments_tC_ha_yr);
      if (initialData.n_synthetic_kgN_ha_yr !== undefined)
        setNFertilizerSynthetic(initialData.n_synthetic_kgN_ha_yr);
      if (initialData.n_organic_kgN_ha_yr !== undefined)
        setNFertilizerOrganic(initialData.n_organic_kgN_ha_yr);
      if (initialData.irrigated !== undefined) setIrrigated(initialData.irrigated);
      if (initialData.weather_source) setWeatherSource(initialData.weather_source);
      if (initialData.weather_sensor_id) setWeatherSensorId(initialData.weather_sensor_id);
    }
  }, [initialData]);

  const handleSave = useCallback(async () => {
    setSaveState('saving');
    setErrorMsg(null);
    try {
      const data: ManagementData = {
        tillage_type: tillageType,
        residues_removed: residuesRemoved,
        cover_crop_months: coverCropMonths,
        organic_amendments_tC_ha_yr: organicAmendments,
        n_synthetic_kgN_ha_yr: nFertilizerSynthetic,
        n_organic_kgN_ha_yr: nFertilizerOrganic,
        irrigated,
        weather_source: weatherSource,
        weather_sensor_id: weatherSource === 'sensor' ? weatherSensorId : undefined,
      };
      await saveManagement(entityId, data);
      setSaveState('saved');
      onSaved?.();
      // Reset save state after 2s
      setTimeout(() => setSaveState('idle'), 2000);
    } catch (err) {
      setSaveState('error');
      setErrorMsg(err instanceof Error ? err.message : t('error'));
    }
  }, [
    entityId,
    tillageType,
    residuesRemoved,
    coverCropMonths,
    organicAmendments,
    nFertilizerSynthetic,
    nFertilizerOrganic,
    irrigated,
    weatherSource,
    weatherSensorId,
    onSaved,
    t,
  ]);

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 10px',
    border: '1px solid #D1D5DB',
    borderRadius: '6px',
    fontSize: '13px',
    color: '#374151',
    backgroundColor: '#FFFFFF',
    boxSizing: 'border-box',
  };

  const labelStyle: React.CSSProperties = {
    fontSize: '12px',
    fontWeight: 500,
    color: '#6B7280',
    marginBottom: '4px',
  };

  const rowStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        handleSave();
      }}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        maxWidth: '100%',
      }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '12px',
        }}
      >
        {/* Tillage type */}
        <div style={rowStyle}>
          <label style={labelStyle}>{t('tillage')}</label>
          <select
            value={tillageType}
            onChange={(e) => setTillageType(e.target.value)}
            style={inputStyle}
          >
            {TILLAGE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(opt.labelKey)}
              </option>
            ))}
          </select>
        </div>

        {/* Cover crop months */}
        <div style={rowStyle}>
          <label style={labelStyle}>{t('cover_crop_months')}</label>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <input
              type="range"
              min={0}
              max={12}
              step={1}
              value={coverCropMonths}
              onChange={(e) => setCoverCropMonths(Number(e.target.value))}
              style={{ flex: 1 }}
            />
            <span
              style={{
                minWidth: '24px',
                textAlign: 'center',
                fontSize: '13px',
                fontWeight: 600,
                color: '#374151',
              }}
            >
              {coverCropMonths}
            </span>
          </div>
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '12px',
        }}
      >
        {/* Organic amendments */}
        <div style={rowStyle}>
          <label style={labelStyle}>{t('organic_amendments')}</label>
          <input
            type="number"
            min={0}
            step={0.1}
            value={organicAmendments}
            onChange={(e) => setOrganicAmendments(Number(e.target.value))}
            style={inputStyle}
          />
        </div>

        {/* N Fertilizer synthetic */}
        <div style={rowStyle}>
          <label style={labelStyle}>{t('n_fertilizer')} (synthetic)</label>
          <input
            type="number"
            min={0}
            step={1}
            value={nFertilizerSynthetic}
            onChange={(e) => setNFertilizerSynthetic(Number(e.target.value))}
            style={inputStyle}
          />
        </div>

        {/* N Fertilizer organic */}
        <div style={rowStyle}>
          <label style={labelStyle}>{t('n_fertilizer')} (organic)</label>
          <input
            type="number"
            min={0}
            step={1}
            value={nFertilizerOrganic}
            onChange={(e) => setNFertilizerOrganic(Number(e.target.value))}
            style={inputStyle}
          />
        </div>
      </div>

      {/* Weather source */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '12px',
        }}
      >
        <div style={rowStyle}>
          <label style={labelStyle}>{t('weather_source')}</label>
          <Select
            value={weatherSource}
            onValueChange={setWeatherSource}
            options={WEATHER_SOURCE_OPTIONS.map((opt) => ({
              value: opt.value,
              label: t(opt.labelKey),
            }))}
            size="sm"
          />
        </div>
        {weatherSource === 'sensor' && (
          <div style={rowStyle}>
            <label style={labelStyle}>{t('select_sensor')}</label>
            <Select
              value={weatherSensorId}
              onValueChange={setWeatherSensorId}
              options={[
                { value: '', label: t('select_sensor') },
                ...sensors.map((s) => ({
                  value: s.id,
                  label: `${s.name}${s.sensor_type ? ` (${s.sensor_type})` : ''}`,
                })),
              ]}
              size="sm"
            />
          </div>
        )}
      </div>

      {/* Toggles */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        <ToggleRow label={t('residues_removed')} checked={residuesRemoved} onChange={setResiduesRemoved} />
        <ToggleRow label={t('irrigated')} checked={irrigated} onChange={setIrrigated} />
      </div>

      {/* Save button + status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          type="submit"
          disabled={saveState === 'saving'}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '10px 20px',
            border: 'none',
            borderRadius: '8px',
            backgroundColor: saveState === 'saved' ? '#059669' : '#2563EB',
            color: '#FFFFFF',
            fontSize: '14px',
            fontWeight: 500,
            cursor: saveState === 'saving' ? 'not-allowed' : 'pointer',
            opacity: saveState === 'saving' ? 0.7 : 1,
            transition: 'all 0.15s ease',
          }}
        >
          {saveState === 'saving' && (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ animation: 'spin 1s linear infinite' }}>
              <circle cx="8" cy="8" r="6" stroke="white" strokeWidth="2" strokeDasharray="8 4" />
            </svg>
          )}
          {saveState === 'saved' ? t('saved') : saveState === 'saving' ? t('saving') : t('save')}
        </button>

        {saveState === 'saved' && (
          <span style={{ fontSize: '13px', color: '#059669', fontWeight: 500 }}>
            {t('saved')}
          </span>
        )}

        {saveState === 'error' && errorMsg && (
          <span style={{ fontSize: '13px', color: '#DC2626' }}>{errorMsg}</span>
        )}
      </div>
    </form>
  );
};

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        cursor: 'pointer',
        fontSize: '13px',
        color: '#374151',
        userSelect: 'none',
      }}
    >
      <div
        onClick={() => onChange(!checked)}
        style={{
          width: '36px',
          height: '20px',
          borderRadius: '10px',
          backgroundColor: checked ? '#2563EB' : '#D1D5DB',
          position: 'relative',
          transition: 'background-color 0.2s ease',
          cursor: 'pointer',
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: '16px',
            height: '16px',
            borderRadius: '50%',
            backgroundColor: '#FFFFFF',
            position: 'absolute',
            top: '2px',
            left: checked ? '18px' : '2px',
            transition: 'left 0.2s ease',
            boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
          }}
        />
      </div>
      {label}
    </label>
  );
}

export default CarbonManagementForm;
