import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from 'react';
import { Icon } from './Icon';
import type { DotKind, TagKind, Role } from '../../lib/types';

/* ---- Bar ---- */
interface BarProps {
  w?: string | number;
  h?: number;
  c?: string;
  style?: CSSProperties;
}
export function Bar({ w = '100%', h = 8, c, style }: BarProps) {
  return (
    <span
      className="bar"
      style={{ width: w, height: h, background: c, ...style }}
    />
  );
}

/* ---- Btn ---- */
interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children?: ReactNode;
  k?: string;
  ic?: string;
  sz?: string;
}
export function Btn({ children, k = '', ic, sz = '', ...p }: BtnProps) {
  return (
    <button className={`btn ${sz} ${k}`.trim()} {...p}>
      {ic && <Icon n={ic} s={14} />}
      {children}
    </button>
  );
}

/* ---- Chip ---- */
interface ChipProps {
  children?: ReactNode;
  on?: boolean;
  ic?: string;
}
export function Chip({ children, on, ic }: ChipProps) {
  return (
    <span className={`chip ${on ? 'on' : ''}`.trim()}>
      {ic && <Icon n={ic} s={12} />}
      {children}
    </span>
  );
}

/* ---- Tag ---- */
interface TagProps {
  children?: ReactNode;
  k: TagKind | string;
}
export function Tag({ children, k }: TagProps) {
  return <span className={`tag ${k}`}>{children}</span>;
}

/* ---- Dot ---- */
interface DotProps {
  k: DotKind | string;
}
export function Dot({ k }: DotProps) {
  return <span className={`dot ${k}`} />;
}

/* ---- Field ---- */
interface FieldProps {
  children?: ReactNode;
  lg?: boolean;
  ic?: string;
  style?: CSSProperties;
}
export function Field({ children, lg, ic = 'search', style }: FieldProps) {
  return (
    <div className={`field ${lg ? 'lg' : ''}`.trim()} style={style}>
      {ic && <Icon n={ic} s={14} c="var(--ink-4)" />}
      <span>{children}</span>
    </div>
  );
}

/* ---- Note ---- */
interface NoteProps {
  children?: ReactNode;
  ink?: boolean;
  style?: CSSProperties;
}
export function Note({ children, ink, style }: NoteProps) {
  return (
    <span className={`note ${ink ? 'ink' : ''}`.trim()} style={style}>
      {children}
    </span>
  );
}

/* ---- Bar/Swatch ---- */
interface SwProps {
  c: string;
  children?: ReactNode;
}
export function Sw({ c, children }: SwProps) {
  return (
    <span className="swatch">
      <i style={{ background: c }} />
      {children}
    </span>
  );
}

/* ---- RoleSwitch ---- */
interface RoleSwitchProps {
  value: Role;
  onChange: (r: Role) => void;
}
export function RoleSwitch({ value, onChange }: RoleSwitchProps) {
  return (
    <div className="roles">
      {([['customer', '客户'], ['employee', '员工'], ['admin', '管理员']] as const).map(([k, l]) => (
        <span
          key={k}
          className={value === k ? 'on' : ''}
          style={{ cursor: 'pointer' }}
          onClick={() => onChange(k as Role)}
        >
          {l}
        </span>
      ))}
    </div>
  );
}

/* ---- Logo ---- */
interface LogoProps {
  dark?: boolean;
}
export function Logo({ dark }: LogoProps) {
  return (
    <div className="logo" style={dark ? { color: '#fff' } : undefined}>
      <span className="mk">
        <Icon n="hex" s={13} c="#fff" />
      </span>
      <span>
        agent<span style={{ color: 'var(--accent)' }}>·</span>forge
      </span>
    </div>
  );
}
