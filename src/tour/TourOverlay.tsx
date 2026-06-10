import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTour } from './TourProvider';
import { TOUR_STEPS, TOUR_TOTAL } from './steps';
import { computePopoverPos, fillReactInput } from './engine';
import { Icon } from '../components/kit/Icon';

interface Rect { top: number; left: number; width: number; height: number; }
const NULL_RECT: Rect = { top: 0, left: 0, width: 0, height: 0 };

const POP_W = 300;
const POP_H = 220; // approximate, used for placement calc

export function TourOverlay() {
  const { state, next, back, skip, finish, targetClicked } = useTour();
  const [rect, setRect] = useState<Rect | null>(null);
  const [waiting, setWaiting] = useState(false);
  const rafRef = useRef<number>(0);
  const missedTimeRef = useRef<number>(0);
  const lastRectRef = useRef<Rect | null>(null);

  const step = state.status === 'running' ? TOUR_STEPS[state.idx] : null;

  // rAF-based target tracking
  const track = useCallback(() => {
    if (!step) return;
    const el = document.querySelector(step.target) as HTMLElement | null;

    if (!el) {
      // Target missing
      const now = performance.now();
      if (missedTimeRef.current === 0) missedTimeRef.current = now;

      if (step.waitForTarget) {
        // Show waiting card
        setWaiting(true);
        setRect(null);
      } else if (now - missedTimeRef.current > 2000) {
        // Non-wait step: degrade to center after 2s
        setRect(NULL_RECT);
        setWaiting(false);
      }
    } else {
      missedTimeRef.current = 0;
      setWaiting(false);
      const r = el.getBoundingClientRect();
      const newRect: Rect = { top: r.top, left: r.left, width: r.width, height: r.height };
      // Only update if changed
      const prev = lastRectRef.current;
      if (!prev || prev.top !== newRect.top || prev.left !== newRect.left ||
          prev.width !== newRect.width || prev.height !== newRect.height) {
        lastRectRef.current = newRect;
        setRect(newRect);
        // Scroll into view on step entry if target is off-screen
        if (missedTimeRef.current === 0) {
          el.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' });
        }
      }
    }

    rafRef.current = requestAnimationFrame(track);
  }, [step]);

  useEffect(() => {
    if (state.status !== 'running') {
      cancelAnimationFrame(rafRef.current);
      setRect(null);
      setWaiting(false);
      return;
    }
    missedTimeRef.current = 0;
    lastRectRef.current = null;
    setRect(null);
    setWaiting(false);
    rafRef.current = requestAnimationFrame(track);
    return () => cancelAnimationFrame(rafRef.current);
  }, [state.status, state.idx, track]);

  // Click capture for 'click' advance steps
  useEffect(() => {
    if (state.status !== 'running' || !step || step.advance !== 'click') return;

    const handler = (e: MouseEvent) => {
      const target = e.target as Element | null;
      if (!target) return;
      // Check if click is within the highlighted element
      const el = document.querySelector(step.target);
      if (el && (el === target || el.contains(target))) {
        setTimeout(() => targetClicked(), 0);
      }
    };
    document.addEventListener('click', handler, true);
    return () => document.removeEventListener('click', handler, true);
  }, [state.status, state.idx, step, targetClicked]);

  // Keyboard shortcuts
  useEffect(() => {
    if (state.status !== 'running') return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') skip();
      else if ((e.key === 'Enter' || e.key === 'ArrowRight') && step?.advance === 'next') {
        e.preventDefault();
        if (state.idx >= TOUR_TOTAL - 1) finish();
        else next();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [state.status, state.idx, step, next, skip, finish]);

  if (state.status !== 'running') return null;
  if (!step) return null;

  const isLastStep = state.idx >= TOUR_TOTAL - 1;
  const isCenterStep = step.placement === 'center' || step.target === 'body';

  // Compute popover position
  const viewport = { w: window.innerWidth, h: window.innerHeight };
  const targetDOMRect = rect
    ? ({ top: rect.top, left: rect.left, right: rect.left + rect.width, bottom: rect.top + rect.height, width: rect.width, height: rect.height } as DOMRect)
    : null;

  const popPos = computePopoverPos(
    isCenterStep ? null : targetDOMRect,
    { w: POP_W, h: POP_H },
    viewport,
    step.placement ?? 'right',
  );

  const showSpotlight = rect && !isCenterStep && !waiting && rect.width > 0;

  return createPortal(
    <>
      {/* Four backdrop pieces forming spotlight */}
      {showSpotlight && rect && (
        <>
          {/* top */}
          <div className="tour-backdrop-piece" style={{ top: 0, left: 0, right: 0, height: rect.top }} />
          {/* bottom */}
          <div className="tour-backdrop-piece" style={{ top: rect.top + rect.height, left: 0, right: 0, bottom: 0 }} />
          {/* left */}
          <div className="tour-backdrop-piece" style={{ top: rect.top, left: 0, width: rect.left, height: rect.height }} />
          {/* right */}
          <div className="tour-backdrop-piece" style={{ top: rect.top, left: rect.left + rect.width, right: 0, height: rect.height }} />
          {/* spotlight ring */}
          <div className="tour-ring" style={{
            top: rect.top - 3, left: rect.left - 3,
            width: rect.width + 6, height: rect.height + 6,
          }} />
        </>
      )}

      {/* Full dim for center/waiting */}
      {(isCenterStep || !showSpotlight) && !waiting && (
        <div className="tour-backdrop-piece" style={{ inset: 0 }} />
      )}

      {/* Waiting card */}
      {waiting && (
        <div className="tour-waiting-card">
          <div className="dot wait" />
          正在等待界面响应…
        </div>
      )}

      {/* Popover card */}
      {!waiting && (
        <div
          className="tour-pop"
          role="dialog"
          aria-label={`教程步骤 ${state.idx + 1}`}
          style={{ top: popPos.top, left: popPos.left, width: POP_W }}
        >
          <div className="tp-head">
            <span className="tp-title">{step.title}</span>
            <span className="tp-step">第 {state.idx + 1} / {TOUR_TOTAL} 步</span>
          </div>
          <div className="tp-body">{step.body}</div>

          {/* Fill button for steps with example text */}
          {step.fill && (
            <button
              className="btn sm"
              style={{ alignSelf: 'flex-start', fontSize: 11 }}
              onClick={() => {
                const el = document.querySelector(step.target) as HTMLInputElement | null;
                if (el) fillReactInput(el, step.fill!);
              }}
            >
              <Icon n="bolt" s={12} />
              填入示例指令
            </button>
          )}

          {step.advance === 'click' && (
            <div className="tp-hint">↑ 点击高亮处继续</div>
          )}

          <div className="tp-foot">
            {state.idx > 0 && (
              <button className="btn ghost sm" onClick={back}>上一步</button>
            )}
            <span className="tf-fill" />
            <button className="btn ghost sm" onClick={skip}>跳过教程</button>
            {step.advance === 'next' && (
              <button
                className="btn pri sm"
                onClick={() => isLastStep ? finish() : next()}
              >
                {isLastStep ? '完成' : '下一步'}
              </button>
            )}
            {step.advance === 'click' && (
              <button className="btn sm" onClick={skip}>跳过此步</button>
            )}
          </div>
        </div>
      )}
    </>,
    document.body,
  );
}
