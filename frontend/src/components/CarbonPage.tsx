import React from 'react';
import { useTranslation } from '@nekazari/sdk';
import { useSearchParams } from 'react-router-dom';
import CarbonBottomPanel from './CarbonBottomPanel';

const CarbonPage: React.FC = () => {
  const { t } = useTranslation('carbon');
  const [searchParams] = useSearchParams();
  const entityId = searchParams.get('entityId') || '';

  if (!entityId) {
    return (
      <div
        style={{
          maxWidth: '960px',
          margin: '0 auto',
          padding: '24px 16px',
          minHeight: '100vh',
        }}
      >
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#111827', marginBottom: '8px' }}>
          {t('title')}
        </h1>
        <p style={{ fontSize: '14px', color: '#6B7280', marginBottom: '24px' }}>
          {t('tier_description')}
        </p>
        <div
          style={{
            textAlign: 'center',
            padding: '60px 20px',
            color: '#9CA3AF',
          }}
        >
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" style={{ marginBottom: '16px' }}>
            <circle cx="24" cy="24" r="22" fill="#E5E7EB" />
            <path d="M16 32L24 16L32 32H16Z" fill="#9CA3AF" />
          </svg>
          <p style={{ fontSize: '14px', maxWidth: '400px', margin: '0 auto', lineHeight: 1.6, color: '#6B7280' }}>
            {t('no_data')}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        maxWidth: '960px',
        margin: '0 auto',
        padding: '24px 16px',
        minHeight: '100vh',
      }}
    >
      <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#111827', marginBottom: '8px' }}>
        {t('title')}
      </h1>
      <p style={{ fontSize: '14px', color: '#6B7280', marginBottom: '24px' }}>
        {t('tier_description')}
      </p>
      <CarbonBottomPanel entityId={entityId} height="auto" />
    </div>
  );
};

export default CarbonPage;
