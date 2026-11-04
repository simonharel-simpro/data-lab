import { defineConfig } from 'astro/config';
import { exportGuard } from './src/integrations/export-guard.ts';

// Static only (S-2): `astro dev` re-reads cards and metrics per request, `astro build` freezes them.
export default defineConfig({
  output: 'static',
  integrations: [exportGuard()],
});
