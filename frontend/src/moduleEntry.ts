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
  viewerSlots: {
    'context-panel': [{
      id: 'carbon-context',
      moduleId: 'carbon',
      component: 'CarbonContextPanel',
      priority: 10,
      localComponent: CarbonContextPanel,
      showWhen: { entityType: ['AgriParcel'] },
    }],
    'dashboard-widget': [{
      id: 'carbon-dashboard',
      moduleId: 'carbon',
      component: 'CarbonDashboardWidget',
      priority: 10,
      localComponent: CarbonDashboardWidget,
    }],
    'bottom-panel': [{
      id: 'carbon-bottom',
      moduleId: 'carbon',
      component: 'CarbonBottomPanel',
      priority: 10,
      localComponent: CarbonBottomPanel,
      showWhen: { entityType: ['AgriParcel'] },
    }],
  },
});

console.log('[nkz-module-carbon] ✅ Registered — id=carbon, version=0.1.0, main page + 3 viewer slots');
