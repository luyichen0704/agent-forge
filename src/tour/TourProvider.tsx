import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { reduce, persistTourState, loadTourState, type TourState } from './engine';
import { TOUR_STEPS, TOUR_TOTAL } from './steps';
import { useApp } from '../lib/appContext';
import { login } from '../features/auth';
import { useMe } from '../features/auth';

interface TourCtxShape {
  state: TourState;
  start: () => Promise<void>;
  next: () => void;
  back: () => void;
  skip: () => void;
  finish: () => void;
  targetClicked: () => void;
}

const TourCtx = createContext<TourCtxShape | null>(null);

export function useTour(): TourCtxShape {
  const ctx = useContext(TourCtx);
  if (!ctx) throw new Error('useTour must be used within TourProvider');
  return ctx;
}

export function TourProvider({ children }: { children: ReactNode }) {
  const { setActive } = useApp();
  const me = useMe();
  const [state, setState] = useState<TourState>(() => {
    const loaded = loadTourState();
    return loaded ?? { status: 'idle', idx: 0 };
  });
  const prevIdxRef = useRef<number>(-1);

  // When step changes, navigate to target screen
  useEffect(() => {
    if (state.status !== 'running') return;
    if (state.idx === prevIdxRef.current) return;
    prevIdxRef.current = state.idx;

    const step = TOUR_STEPS[state.idx];
    if (step?.screen) {
      setActive(step.screen);
    }
    step?.onEnter?.();
  }, [state.status, state.idx, setActive]);

  // Persist when done/skipped
  useEffect(() => {
    if (state.status === 'done' || state.status === 'skipped') {
      persistTourState(state);
    }
  }, [state]);

  const dispatch = useCallback((event: Parameters<typeof reduce>[1]) => {
    setState((s) => reduce(s, event, TOUR_TOTAL));
  }, []);

  const start = useCallback(async () => {
    // Ensure admin before starting
    const role = me.data?.acting_role;
    if (role !== 'admin') {
      await login('admin');
    }
    setState({ status: 'running', idx: 0 });
    prevIdxRef.current = -1; // reset so the first step navigation fires
  }, [me.data]);

  const next = useCallback(() => dispatch('next'), [dispatch]);
  const back = useCallback(() => dispatch('back'), [dispatch]);
  const skip = useCallback(() => dispatch('skip'), [dispatch]);
  const finish = useCallback(() => dispatch('finish'), [dispatch]);
  const targetClicked = useCallback(() => dispatch('targetClicked'), [dispatch]);

  return (
    <TourCtx.Provider value={{ state, start, next, back, skip, finish, targetClicked }}>
      {children}
    </TourCtx.Provider>
  );
}
