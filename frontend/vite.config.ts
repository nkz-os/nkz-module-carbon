import { defineConfig } from 'vite';
import { nkzModulePreset } from '@nekazari/module-builder';

export default defineConfig({
  ...nkzModulePreset(),
  define: {
    // Replace import.meta.env.VITE_API_URL at build time.
    // The @nekazari/module-builder manifest-emit step runs a CJS bundle
    // in Node.js where import.meta.env is undefined.
    'import.meta.env.VITE_API_URL': JSON.stringify(process.env.VITE_API_URL || 'https://nkz.robotika.cloud'),
  },
});
