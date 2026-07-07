import { describe, it, expect } from 'vitest';
import { fmtInt, pct, relTime, shortSourceName } from './format';

describe('fmtInt', () => {
  it('adds thousands separators', () => {
    expect(fmtInt(2161)).toBe('2,161');
    expect(fmtInt(7)).toBe('7');
    expect(fmtInt(1000000)).toBe('1,000,000');
  });
  it('handles non-finite', () => {
    expect(fmtInt(NaN)).toBe('0');
  });
});

describe('pct', () => {
  it('rounds a ratio to integer percent', () => {
    expect(pct(2140, 2161)).toBe(99);
    expect(pct(1, 2)).toBe(50);
  });
  it('returns 0 for zero/invalid whole', () => {
    expect(pct(5, 0)).toBe(0);
    expect(pct(5, -1)).toBe(0);
  });
});

describe('relTime', () => {
  const now = Date.parse('2026-07-07T12:00:00Z');
  it('renders recent times in plain language', () => {
    expect(relTime(now, now)).toBe('刚刚');
    expect(relTime(now - 5 * 60000, now)).toBe('5 分钟前');
    expect(relTime(now - 3 * 3600000, now)).toBe('3 小时前');
    expect(relTime(now - 2 * 86400000, now)).toBe('2 天前');
  });
  it('falls back to a date for old timestamps', () => {
    expect(relTime(Date.parse('2026-06-01T00:00:00Z'), now)).toMatch(/^\d{2}-\d{2}$/);
  });
  it('handles empty input', () => {
    expect(relTime(undefined)).toBe('');
    expect(relTime(null)).toBe('');
  });
});

describe('shortSourceName', () => {
  it('trims to the leading brand token', () => {
    expect(shortSourceName('Gitea (代码托管 / DevOps 平台, 远端US94)')).toBe('Gitea');
    expect(shortSourceName('New API (QuantumNous new-api, LLM 网关/中转平台)')).toBe('New API');
    expect(shortSourceName('数据库')).toBe('数据库');
  });
  it('handles empty', () => {
    expect(shortSourceName(null)).toBe('未知系统');
    expect(shortSourceName('')).toBe('未知系统');
  });
});
