import React from 'react';
import { useTranslation } from '@nekazari/sdk';

interface CarbonTierBadgeProps {
  tier: number;
  confidence: number;
  compact?: boolean;
}

const TIER_COLORS: Record<number, { bg: string; text: string; border: string }> = {
  1: { bg: '#FEF3C7', text: '#92400E', border: '#F59E0B' },
  2: { bg: '#DBEAFE', text: '#1E40AF', border: '#3B82F6' },
  3: { bg: '#D1FAE5', text: '#065F46', border: '#10B981' },
};

function getTierColor(tier: number) {
  return TIER_COLORS[tier] || TIER_COLORS[1];
}

const CarbonTierBadge: React.FC<CarbonTierBadgeProps> = ({
  tier,
  confidence,
  compact = false,
}) => {
  const { t } = useTranslation('carbon');
  const colors = getTierColor(tier);

  if (compact) {
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '2px 8px',
          borderRadius: '4px',
          fontSize: '12px',
          fontWeight: 600,
          backgroundColor: colors.bg,
          color: colors.text,
          border: `1px solid ${colors.border}`,
          whiteSpace: 'nowrap',
        }}
        title={`${t('tier')} ${tier} - ${t('confidence')}: ${confidence.toFixed(1)}%`}
      >
        <span>T{tier}</span>
        <span style={{ fontSize: '10px', opacity: 0.7 }}>|</span>
        <span>{confidence.toFixed(0)}%</span>
      </span>
    );
  }

  return (
    <div
      style={{
        display: 'inline-flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '2px',
        padding: '8px 16px',
        borderRadius: '8px',
        backgroundColor: colors.bg,
        border: `2px solid ${colors.border}`,
      }}
    >
      <span
        style={{
          fontSize: '24px',
          fontWeight: 700,
          color: colors.text,
          lineHeight: 1,
        }}
      >
        {t('tier')} {tier}
      </span>
      <span
        style={{
          fontSize: '12px',
          color: colors.text,
          opacity: 0.8,
        }}
      >
        {t('confidence')}: {confidence.toFixed(1)}%
      </span>
    </div>
  );
};

export default CarbonTierBadge;
