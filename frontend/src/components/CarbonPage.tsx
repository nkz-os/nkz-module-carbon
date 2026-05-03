import React from 'react';
import { useTranslation } from '@nekazari/sdk';
import CarbonBottomPanel from './CarbonBottomPanel';

const CarbonPage: React.FC = () => {
  const { t } = useTranslation('carbon');

  return (
    <div
      style={{
        maxWidth: '960px',
        margin: '0 auto',
        padding: '24px 16px',
        minHeight: '100vh',
      }}
    >
      <h1
        style={{
          fontSize: '24px',
          fontWeight: 700,
          color: '#111827',
          marginBottom: '8px',
        }}
      >
        {t('title')}
      </h1>
      <p
        style={{
          fontSize: '14px',
          color: '#6B7280',
          marginBottom: '24px',
        }}
      >
        {t('tier_description')}
      </p>
      <CarbonBottomPanel height="auto" />
    </div>
  );
};

export default CarbonPage;
