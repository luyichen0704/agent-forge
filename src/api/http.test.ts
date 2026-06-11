import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getToken, setToken, subscribeToken, ApiError } from './http';

describe('http token store', () => {
  beforeEach(() => localStorage.clear());

  it('sets and reads a token', () => {
    expect(getToken()).toBeNull();
    setToken('abc123');
    expect(getToken()).toBe('abc123');
  });

  it('clears the token with null', () => {
    setToken('abc');
    setToken(null);
    expect(getToken()).toBeNull();
  });

  it('ApiError carries status + message', () => {
    const e = new ApiError(403, 'forbidden');
    expect(e.status).toBe(403);
    expect(e.message).toBe('forbidden');
  });
});

describe('subscribeToken', () => {
  it('notifies listeners on setToken (login re-render contract)', () => {
    const fn = vi.fn();
    const unsub = subscribeToken(fn);
    setToken('tok-1');
    expect(fn).toHaveBeenCalledTimes(1);
    setToken(null);
    expect(fn).toHaveBeenCalledTimes(2);
    unsub();
    setToken('tok-2');
    expect(fn).toHaveBeenCalledTimes(2);
    setToken(null);
  });
});
