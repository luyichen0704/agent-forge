import type { CSSProperties } from 'react';

interface IconProps {
  n: string;
  s?: number;
  c?: string;
  sw?: number;
  style?: CSSProperties;
}

const PATHS: Record<string, React.ReactNode> = {
  compass: <><circle cx="12" cy="12" r="9"/><path d="M16 8l-2.5 5.5L8 16l2.5-5.5z"/></>,
  pulse: <path d="M3 12h4l2 6 4-13 2 7h6"/>,
  chat: <path d="M4 5h16v11H9l-4 3v-3H4z"/>,
  flow: <><circle cx="6" cy="6" r="2.4"/><circle cx="6" cy="18" r="2.4"/><circle cx="18" cy="12" r="2.4"/><path d="M8 7l8 4M8 17l8-4"/></>,
  sliders: <><path d="M4 8h10M18 8h2M4 16h2M10 16h10"/><circle cx="16" cy="8" r="2.2"/><circle cx="8" cy="16" r="2.2"/></>,
  shield: <><path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/></>,
  puzzle: <path d="M10 4h4v2.5a1.5 1.5 0 003 0V4h0v0M14 4v0m-4 16H6v-4H3.5a1.5 1.5 0 010-3H6V9h4M14 20h4v-4h2.5a1.5 1.5 0 000-3H18V9h-4"/>,
  hex: <path d="M12 3l7 4v8l-7 4-7-4V7z"/>,
  user: <><circle cx="12" cy="8" r="3.2"/><path d="M5 20c0-3.5 3-6 7-6s7 2.5 7 6"/></>,
  search: <><circle cx="11" cy="11" r="6"/><path d="M20 20l-4-4"/></>,
  plus: <path d="M12 5v14M5 12h14"/>,
  gear: <><circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.5 5.5l2 2M16.5 16.5l2 2M18.5 5.5l-2 2M7.5 16.5l-2 2"/></>,
  chevron: <path d="M9 6l6 6-6 6"/>,
  chevd: <path d="M6 9l6 6 6-6"/>,
  bell: <path d="M6 9a6 6 0 0112 0c0 5 2 6 2 6H4s2-1 2-6M10 20a2 2 0 004 0"/>,
  check: <path d="M5 12l4 4 10-10"/>,
  doc: <><path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4"/></>,
  db: <><ellipse cx="12" cy="6" rx="7" ry="2.8"/><path d="M5 6v12c0 1.5 3 2.8 7 2.8s7-1.3 7-2.8V6"/><path d="M5 12c0 1.5 3 2.8 7 2.8s7-1.3 7-2.8"/></>,
  code: <path d="M9 7l-5 5 5 5M15 7l5 5-5 5"/>,
  globe: <><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/></>,
  x: <path d="M6 6l12 12M18 6L6 18"/>,
  dots: <><circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/></>,
  play: <path d="M7 5l12 7-12 7z"/>,
  refresh: <path d="M4 12a8 8 0 0114-5l2 2M20 12a8 8 0 01-14 5l-2-2M18 4v5h-5M6 20v-5h5"/>,
  link: <path d="M9 15l6-6M8 9H6a3 3 0 000 6h2M16 15h2a3 3 0 000-6h-2"/>,
  eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="2.6"/></>,
  filter: <path d="M3 5h18l-7 8v6l-4-2v-4z"/>,
  bolt: <path d="M13 3L5 13h6l-1 8 8-11h-6z"/>,
  lock: <><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 018 0v3"/></>,
  table: <><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M3 14h18M9 4v16"/></>,
  branch: <><circle cx="6" cy="6" r="2.2"/><circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="8" r="2.2"/><path d="M6 8v8M6 12h6a4 4 0 004-4"/></>,
  help: <><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 015 0c0 2-3 2.5-3 4"/><circle cx="12" cy="17" r=".8" fill="currentColor" stroke="none"/></>,
  logout: <><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></>,
  bars: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
  grid: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
  layers: <><path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/></>,
  spark: <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M18 6l-2.5 2.5M8.5 15.5L6 18"/>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"/></>,
  moon: <path d="M21 12.8A8.5 8.5 0 1111.2 3a6.6 6.6 0 009.8 9.8z"/>,
  monitor: <><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></>,
};

export function Icon({ n, s = 18, c = 'currentColor', sw = 1.7, style }: IconProps) {
  return (
    <svg
      width={s}
      height={s}
      viewBox="0 0 24 24"
      fill="none"
      stroke={c}
      strokeWidth={sw}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flex: '0 0 auto', ...style }}
    >
      {PATHS[n] ?? PATHS.dots}
    </svg>
  );
}
