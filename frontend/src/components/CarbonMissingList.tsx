import React from 'react';
import { useTranslation } from '@nekazari/sdk';
import type { MissingItem } from '../api/carbonApi';
import { colors } from './styles';

interface CarbonMissingListProps {
  missing: MissingItem[];
  maxItems?: number;
}

/** What the balance could not use, and what that blocks. Never hidden. */
const CarbonMissingList: React.FC<CarbonMissingListProps> = ({ missing, maxItems }) => {
  const { t } = useTranslation('carbon');
  const unique = missing.filter((m, i) => missing.findIndex((o) => o.item === m.item) === i);
  const shown = maxItems ? unique.slice(0, maxItems) : unique;
  const rest = unique.length - shown.length;

  if (unique.length === 0) {
    return (
      <div style={{ padding: '8px 12px', backgroundColor: colors.accentSoft, borderRadius: '6px',
        color: colors.accentStrong, fontSize: '13px' }}>
        {t('missing_none')}
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      {shown.map((m) => (
        <div key={m.item} style={{ padding: '8px 10px', backgroundColor: colors.bgSubtle, borderRadius: '6px',
          border: `1px solid ${colors.border}` }}>
          <div style={{ fontSize: '13px', fontWeight: 500, color: colors.textPrimary }}>
            {t(`missing.${m.item}`, { defaultValue: m.item })}
          </div>
          <div style={{ fontSize: '11px', color: colors.textSecondary }}>
            {t(`effect.${m.effect}`, { defaultValue: m.effect })}
          </div>
        </div>
      ))}
      {rest > 0 && (
        <div style={{ fontSize: '11px', color: colors.textMuted }}>{t('missing_more', { count: rest })}</div>
      )}
    </div>
  );
};

export default CarbonMissingList;
