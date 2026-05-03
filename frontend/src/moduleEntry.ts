import './i18n';
import CarbonContextPanel from './components/CarbonContextPanel';
import CarbonDashboardWidget from './components/CarbonDashboardWidget';
import CarbonBottomPanel from './components/CarbonBottomPanel';

const NKZ = (window as any).__NKZ__;

NKZ.register({
  id: 'carbon',
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
