import { defineConfig } from 'vite';
import { nkzModulePreset } from '@nekazari/module-builder';

export default defineConfig(
  nkzModulePreset({
    moduleId: 'carbon',
    entry: 'src/moduleEntry.ts',
  }),
);
