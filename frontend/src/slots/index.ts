import CarbonContextPanel from '../components/CarbonContextPanel';
import CarbonDashboardWidget from '../components/CarbonDashboardWidget';

const MODULE_ID = 'carbon';

export const moduleSlots = {
  'context-panel': [
    {
      id: 'carbon-context',
      moduleId: MODULE_ID,
      component: 'CarbonContextPanel',
      localComponent: CarbonContextPanel,
      priority: 10,
      showWhen: { entityType: ['AgriParcel'] },
    },
  ],
  'dashboard-widget': [
    {
      id: 'carbon-dashboard',
      moduleId: MODULE_ID,
      component: 'CarbonDashboardWidget',
      localComponent: CarbonDashboardWidget,
      priority: 10,
    },
  ],
};
