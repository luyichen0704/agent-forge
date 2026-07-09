/* Theme store — light / dark / follow-system, persisted to localStorage.
 *
 * The *applied* theme is reflected on <html data-theme>:
 *   · 'light' | 'dark' → sets the attribute (overrides the OS preference)
 *   · 'system'         → removes the attribute so the prefers-color-scheme
 *                        media query in index.css governs the palette.
 *
 * A tiny inline script in index.html stamps data-theme before first paint to
 * avoid a flash of the wrong theme; this module reconciles the DOM on startup
 * and notifies React subscribers via useSyncExternalStore. */

export type ThemePref = 'light' | 'dark' | 'system';
export type EffectiveTheme = 'light' | 'dark';

export const THEME_KEY = 'af-theme';

const listeners = new Set<() => void>();

function isPref(v: unknown): v is ThemePref {
  return v === 'light' || v === 'dark' || v === 'system';
}

function readStored(): ThemePref {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return isPref(v) ? v : 'system';
  } catch {
    return 'system';
  }
}

function systemPrefersDark(): boolean {
  try {
    return typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-color-scheme: dark)').matches;
  } catch {
    return false;
  }
}

/** Reflect the preference onto <html>: explicit sets data-theme, 'system' clears it. */
function reflect(pref: ThemePref): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  if (pref === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', pref);
}

let current: ThemePref = readStored();

export function getThemePref(): ThemePref {
  return current;
}

/** The palette actually in effect right now (resolves 'system' against the OS). */
export function getEffectiveTheme(): EffectiveTheme {
  return current === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : current;
}

function emit(): void {
  listeners.forEach((l) => l());
}

export function setThemePref(pref: ThemePref): void {
  if (!isPref(pref)) return;
  current = pref;
  try { localStorage.setItem(THEME_KEY, pref); } catch { /* storage unavailable */ }
  reflect(pref);
  emit();
}

export function subscribeTheme(cb: () => void): () => void {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

let wired = false;

/** Call once at startup: reconcile the DOM with the stored pref and wire
 *  OS-scheme + cross-tab synchronisation. Idempotent. */
export function initTheme(): void {
  current = readStored();
  reflect(current);
  if (wired || typeof window === 'undefined') return;
  wired = true;

  if (typeof window.matchMedia === 'function') {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onOS = () => { if (current === 'system') emit(); };
    if (mq.addEventListener) mq.addEventListener('change', onOS);
    else if (mq.addListener) mq.addListener(onOS); // Safari < 14
  }

  window.addEventListener('storage', (e) => {
    if (e.key === THEME_KEY) {
      current = readStored();
      reflect(current);
      emit();
    }
  });
}
