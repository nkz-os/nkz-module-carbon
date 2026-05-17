import { defineModule } from '@nekazari/module-kit';
import { lazy } from 'react';
import './i18n';
import { moduleSlots } from './slots';
import pkg from '../package.json';

const MainPage = lazy(() => import('./components/CarbonPage'));

export default defineModule({
  id: 'carbon',
  displayName: 'Carbon Intelligence',
  version: pkg.version,
  hostApiVersion: '^2.0.0',
  description: '3-tier carbon engine: RothC, GHG, MRV — Nekazari Platform Module',
  accent: { base: '#16A34A', soft: '#DCFCE7', strong: '#14532D' },
  icon: 'leaf',
  main: MainPage,
  api: { basePath: '/api/carbon' },
  slots: moduleSlots as never,
});
