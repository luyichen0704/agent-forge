/* Pure-function tour state machine — React-agnostic, fully unit-testable. */

export type TourStatus = 'idle' | 'running' | 'done' | 'skipped';

export interface TourState {
  status: TourStatus;
  idx: number;
}

export type TourEvent = 'start' | 'next' | 'back' | 'skip' | 'targetClicked' | 'finish';

const TOUR_KEY = 'agentforge.tour.v1';
const WELCOME_KEY = 'agentforge.welcome.v1';

export function reduce(state: TourState, event: TourEvent, total: number): TourState {
  if (state.status !== 'running' && event !== 'start') {
    return state;
  }
  switch (event) {
    case 'start':
      return { status: 'running', idx: 0 };
    case 'next': {
      const next = state.idx + 1;
      if (next >= total) return { status: 'done', idx: state.idx };
      return { status: 'running', idx: next };
    }
    case 'back':
      return { status: 'running', idx: Math.max(0, state.idx - 1) };
    case 'skip':
      return { status: 'skipped', idx: state.idx };
    case 'targetClicked': {
      const next = state.idx + 1;
      if (next >= total) return { status: 'done', idx: state.idx };
      return { status: 'running', idx: next };
    }
    case 'finish':
      return { status: 'done', idx: state.idx };
    default:
      return state;
  }
}

export function persistTourState(s: TourState): void {
  localStorage.setItem(TOUR_KEY, JSON.stringify(s));
}

export function loadTourState(): TourState | null {
  try {
    const raw = localStorage.getItem(TOUR_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as TourState;
  } catch {
    return null;
  }
}

export function markWelcomeSeen(): void {
  localStorage.setItem(WELCOME_KEY, 'seen');
}

export function shouldOfferOnboarding(): boolean {
  if (localStorage.getItem(WELCOME_KEY) === 'seen') return false;
  const ts = loadTourState();
  if (ts && (ts.status === 'done' || ts.status === 'skipped')) return false;
  return true;
}

export interface PopoverPos {
  left: number;
  top: number;
}

export function computePopoverPos(
  targetRect: DOMRect | null,
  popSize: { w: number; h: number },
  viewport: { w: number; h: number },
  placement: 'right' | 'left' | 'top' | 'bottom' | 'center',
): PopoverPos {
  if (!targetRect) {
    // center fallback
    return {
      left: (viewport.w - popSize.w) / 2,
      top: (viewport.h - popSize.h) / 2,
    };
  }

  const GAP = 14;
  let left = 0;
  let top = 0;

  if (placement === 'right' || placement === 'left') {
    // Prefer right, flip to left if not enough room
    const rightLeft = targetRect.right + GAP;
    const leftLeft = targetRect.left - GAP - popSize.w;

    if (placement === 'right' && rightLeft + popSize.w <= viewport.w) {
      left = rightLeft;
    } else if (leftLeft >= 0) {
      left = leftLeft;
    } else {
      left = rightLeft;
    }
    // Vertical center aligned with target
    top = targetRect.top + targetRect.height / 2 - popSize.h / 2;
  } else if (placement === 'top' || placement === 'bottom') {
    left = targetRect.left + targetRect.width / 2 - popSize.w / 2;
    if (placement === 'bottom') {
      top = targetRect.bottom + GAP;
      if (top + popSize.h > viewport.h) {
        top = targetRect.top - GAP - popSize.h;
      }
    } else {
      top = targetRect.top - GAP - popSize.h;
      if (top < 0) {
        top = targetRect.bottom + GAP;
      }
    }
  } else {
    // center
    left = (viewport.w - popSize.w) / 2;
    top = (viewport.h - popSize.h) / 2;
  }

  // Clamp to viewport
  const PAD = 10;
  left = Math.max(PAD, Math.min(left, viewport.w - popSize.w - PAD));
  top = Math.max(PAD, Math.min(top, viewport.h - popSize.h - PAD));

  return { left, top };
}

/** Set a React-controlled input's value via native setter + bubbled input event. */
export function fillReactInput(el: HTMLInputElement, text: string): void {
  const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'value',
  )?.set;
  if (nativeInputValueSetter) {
    nativeInputValueSetter.call(el, text);
  } else {
    el.value = text;
  }
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}
