/** Shared state between carbon module slots. */
import type { ManagementData } from '../api/carbonApi';

interface CarbonState {
  managementData: ManagementData | null;
}

const state: CarbonState = { managementData: null };

export function getManagementData(): ManagementData | null {
  return state.managementData;
}

export function setManagementData(data: ManagementData | null) {
  state.managementData = data;
}
