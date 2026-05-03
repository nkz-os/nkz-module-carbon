import React from 'react';
import { useTranslation } from '@nekazari/sdk';
import type { GapItem } from '../api/carbonApi';

interface CarbonGapListProps {
  gaps: GapItem[];
  missingForNextTier: string[];
  maxItems?: number;
}

const CarbonGapList: React.FC<CarbonGapListProps> = ({
  gaps,
  missingForNextTier,
  maxItems,
}) => {
  const { t } = useTranslation('carbon');

  const openGaps = gaps.filter((g) => g.missing);
  const displayGaps = maxItems ? openGaps.slice(0, maxItems) : openGaps;
  const remaining = maxItems ? Math.max(0, openGaps.length - maxItems) : 0;

  if (openGaps.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '8px 12px',
          backgroundColor: '#F0FDF4',
          borderRadius: '6px',
          color: '#166534',
          fontSize: '13px',
          fontWeight: 500,
        }}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          style={{ flexShrink: 0 }}
        >
          <circle cx="8" cy="8" r="7" fill="#22C55E" />
          <path
            d="M5 8.5L7 10.5L11 6"
            stroke="white"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span>{t('no_gaps')}</span>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      {missingForNextTier.length > 0 && (
        <div
          style={{
            fontSize: '11px',
            fontWeight: 600,
            color: '#6B7280',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
            marginBottom: '4px',
          }}
        >
          {t('missing_for_next_tier')}
        </div>
      )}
      {displayGaps.map((gap, idx) => (
        <div
          key={`${gap.source}-${idx}`}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '8px',
            padding: '6px 10px',
            backgroundColor: '#FFFBEB',
            borderRadius: '4px',
            border: '1px solid #FDE68A',
            fontSize: '13px',
            flexWrap: 'wrap',
            minWidth: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ flexShrink: 0 }}>
              <circle cx="7" cy="7" r="6" fill="#F59E0B" />
              <path d="M7 4.5V8M7 9.5V9.505" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <span style={{ fontWeight: 500, color: '#92400E' }}>{gap.source}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
            {gap.auto_fill && (
              <span
                style={{
                  fontSize: '11px',
                  padding: '1px 6px',
                  borderRadius: '3px',
                  backgroundColor: '#DBEAFE',
                  color: '#1E40AF',
                }}
              >
                {gap.auto_fill}
              </span>
            )}
          </div>
        </div>
      ))}
      {remaining > 0 && (
        <div
          style={{
            fontSize: '12px',
            color: '#6B7280',
            textAlign: 'center',
            padding: '2px 0',
          }}
        >
          +{remaining} {t('gaps').toLowerCase()}
        </div>
      )}
    </div>
  );
};

export default CarbonGapList;
