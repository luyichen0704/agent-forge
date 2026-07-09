import { useSyncExternalStore } from 'react';
import { Icon } from './kit';
import {
  getThemePref, subscribeTheme, setThemePref, type ThemePref,
} from '../lib/theme';

const OPTIONS: Array<{ k: ThemePref; icon: string; label: string; aria: string }> = [
  { k: 'light', icon: 'sun', label: '亮', aria: '亮色主题' },
  { k: 'dark', icon: 'moon', label: '暗', aria: '暗色主题' },
  { k: 'system', icon: 'monitor', label: '系统', aria: '跟随系统' },
];

/** Three-state appearance switch: 亮 / 暗 / 跟随系统. Persists to localStorage. */
export function ThemeToggle() {
  const pref = useSyncExternalStore(subscribeTheme, getThemePref, getThemePref);
  return (
    <div className="theme-seg" role="group" aria-label="外观主题">
      {OPTIONS.map((o) => (
        <button
          key={o.k}
          type="button"
          className={pref === o.k ? 'on' : ''}
          aria-label={o.aria}
          aria-pressed={pref === o.k}
          title={o.aria}
          onClick={() => setThemePref(o.k)}
        >
          <Icon n={o.icon} s={13} />
          {o.label}
        </button>
      ))}
    </div>
  );
}
