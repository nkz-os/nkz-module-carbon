import './i18n';
import CarbonPage from './components/CarbonPage';
import CarbonContextPanel from './components/CarbonContextPanel';
import CarbonDashboardWidget from './components/CarbonDashboardWidget';
import CarbonBottomPanel from './components/CarbonBottomPanel';

const NKZ = (window as any).__NKZ__;

NKZ.register({
  id: 'carbon',
  version: '0.1.0',
  main: CarbonPage,
  viewerSlots: [
    {
      slot: 'context-panel',
      component: CarbonContextPanel,
      height: 'auto',
    },
    {
      slot: 'dashboard-widget',
      component: CarbonDashboardWidget,
      dimensions: { minW: 2, minH: 2 },
    },
    {
      slot: 'bottom-panel',
      component: CarbonBottomPanel,
      height: 400,
    },
  ],
});
