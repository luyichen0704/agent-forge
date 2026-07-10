/**
 * Demo mode installer — called once before React renders.
 * Sets the DemoAdapter on http.ts and patches window.EventSource.
 */

import { setDemoAdapter } from '../api/http';
import { defaultDispatch } from './router';
import { installEventSourcePatch } from './sse';

export function installDemo(): void {
  // 1. Replace all HTTP traffic with demo adapter
  setDemoAdapter(defaultDispatch);

  // 2. Patch EventSource for exploration SSE
  installEventSourcePatch();
}
