import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  THEME_KEY, getThemePref, getEffectiveTheme, setThemePref, subscribeTheme, initTheme,
} from './theme';

/** jsdom has no matchMedia — install a controllable stub. */
function mockMatchMedia(dark: boolean) {
  window.matchMedia = vi.fn().mockImplementation((q: string) => ({
    matches: q.includes('dark') ? dark : false,
    media: q,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

describe('theme store', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    mockMatchMedia(false);
    setThemePref('system'); // reset singleton state
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('defaults to "system" with no stored preference', () => {
    initTheme();
    expect(getThemePref()).toBe('system');
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('forcing dark writes localStorage and stamps <html data-theme="dark">', () => {
    setThemePref('dark');
    expect(getThemePref()).toBe('dark');
    expect(localStorage.getItem(THEME_KEY)).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('forcing light stamps data-theme="light"', () => {
    setThemePref('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(localStorage.getItem(THEME_KEY)).toBe('light');
  });

  it('switching back to system removes the attribute (media query governs)', () => {
    setThemePref('dark');
    setThemePref('system');
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
    expect(localStorage.getItem(THEME_KEY)).toBe('system');
  });

  it('effective theme resolves "system" against the OS preference', () => {
    mockMatchMedia(true);
    setThemePref('system');
    expect(getEffectiveTheme()).toBe('dark');

    mockMatchMedia(false);
    // getEffectiveTheme re-reads matchMedia each call
    expect(getEffectiveTheme()).toBe('light');
  });

  it('explicit preference overrides the OS in effective theme', () => {
    mockMatchMedia(true); // OS says dark
    setThemePref('light');
    expect(getEffectiveTheme()).toBe('light');
  });

  it('notifies subscribers on change and stops after unsubscribe', () => {
    const cb = vi.fn();
    const off = subscribeTheme(cb);
    setThemePref('dark');
    expect(cb).toHaveBeenCalledTimes(1);
    off();
    setThemePref('light');
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it('initTheme reflects a previously stored preference onto <html>', () => {
    localStorage.setItem(THEME_KEY, 'dark');
    initTheme();
    expect(getThemePref()).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('ignores a corrupt stored value and falls back to system', () => {
    localStorage.setItem(THEME_KEY, 'chartreuse');
    initTheme();
    expect(getThemePref()).toBe('system');
  });
});
