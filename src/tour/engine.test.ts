import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  reduce,
  loadTourState,
  persistTourState,
  shouldOfferOnboarding,
  computePopoverPos,
  fillReactInput,
  type TourState,
} from './engine';

const TOTAL = 17;

function idle(): TourState { return { status: 'idle', idx: 0 }; }
function running(idx: number): TourState { return { status: 'running', idx }; }

// ---- reduce ----
describe('reduce', () => {
  it('start moves idle → running idx=0', () => {
    expect(reduce(idle(), 'start', TOTAL)).toEqual({ status: 'running', idx: 0 });
  });

  it('next advances idx', () => {
    expect(reduce(running(3), 'next', TOTAL)).toEqual({ status: 'running', idx: 4 });
  });

  it('next on last step → done', () => {
    expect(reduce(running(TOTAL - 1), 'next', TOTAL)).toEqual({ status: 'done', idx: TOTAL - 1 });
  });

  it('back decrements idx, floor 0', () => {
    expect(reduce(running(5), 'back', TOTAL)).toEqual({ status: 'running', idx: 4 });
    expect(reduce(running(0), 'back', TOTAL)).toEqual({ status: 'running', idx: 0 });
  });

  it('skip → skipped', () => {
    expect(reduce(running(3), 'skip', TOTAL)).toEqual({ status: 'skipped', idx: 3 });
  });

  it('finish → done', () => {
    expect(reduce(running(16), 'finish', TOTAL)).toEqual({ status: 'done', idx: 16 });
  });

  it('targetClicked advances if advance==="click" implied (checked externally)', () => {
    // The engine only fires targetClicked for click-advance steps; the caller checks step.advance.
    // Here we test that the event does advance the state.
    expect(reduce(running(2), 'targetClicked', TOTAL)).toEqual({ status: 'running', idx: 3 });
  });

  it('no-op events on non-running state', () => {
    const done: TourState = { status: 'done', idx: 5 };
    expect(reduce(done, 'next', TOTAL)).toEqual(done);
    expect(reduce(done, 'back', TOTAL)).toEqual(done);
  });
});

// ---- persist / load ----
describe('persistTourState / loadTourState', () => {
  beforeEach(() => localStorage.clear());

  it('round-trips a done state', () => {
    const s: TourState = { status: 'done', idx: 16 };
    persistTourState(s);
    expect(loadTourState()).toEqual(s);
  });

  it('round-trips a skipped state', () => {
    const s: TourState = { status: 'skipped', idx: 5 };
    persistTourState(s);
    expect(loadTourState()).toEqual(s);
  });

  it('returns null when nothing stored', () => {
    expect(loadTourState()).toBeNull();
  });
});

// ---- shouldOfferOnboarding ----
describe('shouldOfferOnboarding', () => {
  beforeEach(() => localStorage.clear());

  it('true when both keys absent', () => {
    expect(shouldOfferOnboarding()).toBe(true);
  });

  it('false when welcome already seen', () => {
    localStorage.setItem('agentforge.welcome.v1', 'seen');
    expect(shouldOfferOnboarding()).toBe(false);
  });

  it('false when tour done', () => {
    persistTourState({ status: 'done', idx: 16 });
    expect(shouldOfferOnboarding()).toBe(false);
  });
});

// ---- computePopoverPos ----
describe('computePopoverPos', () => {
  const popSize = { w: 300, h: 200 };
  const viewport = { w: 1200, h: 800 };

  it('places to the right of target when there is space', () => {
    const target = { left: 100, top: 300, right: 200, bottom: 360, width: 100, height: 60 };
    const pos = computePopoverPos(target as DOMRect, popSize, viewport, 'right');
    expect(pos.left).toBeGreaterThan(200);
    expect(pos.top).toBeGreaterThanOrEqual(0);
  });

  it('flips to left when right space is insufficient', () => {
    const target = { left: 1000, top: 300, right: 1100, bottom: 360, width: 100, height: 60 };
    const pos = computePopoverPos(target as DOMRect, popSize, viewport, 'right');
    expect(pos.left).toBeLessThan(1000);
  });

  it('centers when target is null', () => {
    const pos = computePopoverPos(null, popSize, viewport, 'right');
    expect(pos.left).toBeCloseTo((viewport.w - popSize.w) / 2, -1);
    expect(pos.top).toBeCloseTo((viewport.h - popSize.h) / 2, -1);
  });
});

// ---- fillReactInput ----
describe('fillReactInput', () => {
  it('sets value and fires input event on an input element', () => {
    const el = document.createElement('input');
    document.body.appendChild(el);
    const events: string[] = [];
    el.addEventListener('input', () => events.push('input'));
    el.addEventListener('change', () => events.push('change'));
    fillReactInput(el, 'hello world');
    expect(el.value).toBe('hello world');
    expect(events).toContain('input');
    document.body.removeChild(el);
  });
});
