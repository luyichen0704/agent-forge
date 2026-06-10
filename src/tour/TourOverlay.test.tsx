import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TourProvider, useTour } from './TourProvider';
import { TourOverlay } from './TourOverlay';
import { AppProvider } from '../lib/appContext';

// Stub requestAnimationFrame
let rafCallbacks: FrameRequestCallback[] = [];
beforeEach(() => {
  rafCallbacks = [];
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    rafCallbacks.push(cb);
    return rafCallbacks.length;
  });
  vi.stubGlobal('cancelAnimationFrame', () => {});
  // Stub fetch so login('admin') doesn't fail
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : {};
    if (String(url).includes('/auth/login') || String(url).includes('/auth/token')) {
      return new Response(JSON.stringify({ token: 'test-token' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (String(url).includes('/me')) {
      return new Response(JSON.stringify({ id: '1', acting_role: 'admin', allowed_screens: ['chat', 'flow', 'ops', 'audit', 'explore', 'live', 'plugins'] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function flushRaf(times = 5) {
  for (let i = 0; i < times; i++) {
    const cbs = [...rafCallbacks];
    rafCallbacks = [];
    cbs.forEach((cb) => cb(performance.now()));
  }
}

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <AppProvider>
        <TourProvider>
          {children}
          <TourOverlay />
        </TourProvider>
      </AppProvider>
    </QueryClientProvider>
  );
}

function StartButton() {
  const { state, next, skip, start } = useTour();
  return (
    <div>
      <button onClick={() => start()}>Start Tour</button>
      <button onClick={next}>Next</button>
      <button onClick={skip}>Skip</button>
      <div data-testid="status">{state.status}</div>
      <div data-testid="idx">{state.idx}</div>
    </div>
  );
}

describe('TourOverlay', () => {
  it('renders nothing when status is idle', () => {
    render(<Wrapper><StartButton /></Wrapper>);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows popover after start', async () => {
    render(<Wrapper><StartButton /></Wrapper>);
    await act(async () => {
      fireEvent.click(screen.getByText('Start Tour'));
    });
    await act(async () => { flushRaf(); });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('advances on next button click', async () => {
    render(<Wrapper><StartButton /></Wrapper>);
    await act(async () => { fireEvent.click(screen.getByText('Start Tour')); });
    await act(async () => { flushRaf(); });

    expect(screen.getByTestId('idx').textContent).toBe('0');
    await act(async () => { fireEvent.click(screen.getByText('下一步')); });
    expect(screen.getByTestId('idx').textContent).toBe('1');
  });

  it('skip sets status to skipped', async () => {
    render(<Wrapper><StartButton /></Wrapper>);
    await act(async () => { fireEvent.click(screen.getByText('Start Tour')); });
    await act(async () => { flushRaf(); });

    await act(async () => { fireEvent.click(screen.getByText('跳过教程')); });
    expect(screen.getByTestId('status').textContent).toBe('skipped');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows step count in dialog', async () => {
    render(<Wrapper><StartButton /></Wrapper>);
    await act(async () => { fireEvent.click(screen.getByText('Start Tour')); });
    await act(async () => { flushRaf(); });

    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('第 1 / 17 步');
  });

  it('click-advance step: clicking target advances step', async () => {
    // Set up a fake target element for step with advance=click
    const el = document.createElement('button');
    el.setAttribute('data-tour', 'chat-send');
    document.body.appendChild(el);

    render(<Wrapper><StartButton /></Wrapper>);
    await act(async () => { fireEvent.click(screen.getByText('Start Tour')); });
    await act(async () => { flushRaf(); });

    // Advance to step index 2 (chat-send, advance=click)
    // Use the Next button exposed by our StartButton
    await act(async () => { fireEvent.click(screen.getByText('Next')); }); // 0→1
    await act(async () => { fireEvent.click(screen.getByText('Next')); }); // 1→2
    expect(screen.getByTestId('idx').textContent).toBe('2');

    // At step 2 (chat-send), clicking target should advance
    await act(async () => {
      flushRaf();
      el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, composed: true }));
    });
    await act(async () => { flushRaf(); });
    expect(screen.getByTestId('idx').textContent).toBe('3');

    document.body.removeChild(el);
  });
});
