import './i18n';
import CarbonPage from './components/CarbonPage';
import CarbonContextPanel from './components/CarbonContextPanel';
import CarbonDashboardWidget from './components/CarbonDashboardWidget';
import CarbonBottomPanel from './components/CarbonBottomPanel';

console.log('[nkz-module-carbon] Bundle loaded v0.1.0');
console.log('[nkz-module-carbon] __NKZ__:', typeof (window as any).__NKZ__);

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

console.log('[nkz-module-carbon] Registered with main +', NKZ.getRegistration('carbon')?.viewerSlots?.length, 'slots');
