import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AppProvider } from '../lib/appContext';
import { Shell } from './Shell';
import { NAV } from '../lib/data';

function renderShell() {
  return render(
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}

describe('Shell — rail icons', () => {
  it('renders 7 rail icons (one per NAV entry)', () => {
    renderShell();
    const navIconTitles = NAV.map(n => n.cn);
    const ricons = document.querySelectorAll('.ricon');
    const foundNavIcons = Array.from(ricons).filter(el =>
      navIconTitles.some(cn => (el as HTMLElement).title?.startsWith(cn))
    );
    expect(foundNavIcons).toHaveLength(7);
  });

  it('clicking an allowed rail icon switches active screen (explore→chat)', () => {
    renderShell();
    // Default role is admin, default active is 'explore'
    // Find chat icon (cn='对话') and click it
    const chatIcon = document.querySelector('[title^="对话"]') as HTMLElement;
    expect(chatIcon).toBeTruthy();
    fireEvent.click(chatIcon);
    // After clicking chat, the topbar shows the chat screen title (h2)
    const h2elements = screen.getAllByText('张伟退款加急');
    // At least one should be the h2 screen title
    expect(h2elements.length).toBeGreaterThanOrEqual(1);
  });

  it('clicking a disallowed rail icon does nothing (customer role)', () => {
    renderShell();
    // Switch to customer role (label '客户')
    const customerBtn = screen.getByText('客户');
    fireEvent.click(customerBtn);

    // 'explore' icon should be disabled for customer
    const exploreIcon = document.querySelector('[title^="探索配置"]') as HTMLElement;
    expect(exploreIcon).toBeTruthy();
    expect(exploreIcon.style.opacity).toBe('0.3');
    expect(exploreIcon.style.cursor).toBe('not-allowed');

    // Clicking it should NOT change screen
    fireEvent.click(exploreIcon);
    // Screen title should still show chat (default for customer)
    const chatTitles = screen.getAllByText('张伟退款加急');
    expect(chatTitles.length).toBeGreaterThanOrEqual(1);
  });
});

describe('Shell — search + subnav', () => {
  it('typing in search filters the subnav rows', () => {
    renderShell();
    // admin/explore default; subnav has DatabaseExplorer etc.
    expect(screen.getByText('DatabaseExplorer')).toBeInTheDocument();
    const input = screen.getByLabelText('搜索') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Database' } });
    expect(screen.getByText('DatabaseExplorer')).toBeInTheDocument();
    expect(screen.queryByText('APIExplorer')).toBeNull();
  });

  it('no-match search shows empty hint', () => {
    renderShell();
    const input = screen.getByLabelText('搜索') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'zzz-nope' } });
    expect(screen.getByText('无匹配项')).toBeInTheDocument();
  });

  it('switching screen clears the search query', () => {
    renderShell();
    const input = screen.getByLabelText('搜索') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'Database' } });
    expect(input.value).toBe('Database');
    fireEvent.click(document.querySelector('[title^="对话"]') as HTMLElement);
    const input2 = screen.getByLabelText('搜索') as HTMLInputElement;
    expect(input2.value).toBe('');
  });
});

describe('Shell — role differentiation', () => {
  it('customer role: only chat+flow nav enabled (others at opacity 0.3 / not-allowed)', () => {
    renderShell();
    const customerBtn = screen.getByText('客户');
    fireEvent.click(customerBtn);

    const allowedKeys = ['chat', 'flow'];
    const disabledKeys = ['explore', 'live', 'ops', 'audit', 'plugins'];

    for (const item of NAV) {
      const icon = document.querySelector(`[title^="${item.cn}"]`) as HTMLElement;
      if (disabledKeys.includes(item.k)) {
        expect(icon?.style.opacity, `${item.k} should be disabled`).toBe('0.3');
        expect(icon?.style.cursor, `${item.k} should be not-allowed`).toBe('not-allowed');
      } else if (allowedKeys.includes(item.k)) {
        expect(icon?.style.opacity, `${item.k} should be enabled`).not.toBe('0.3');
        expect(icon?.style.cursor, `${item.k} should be pointer`).toBe('pointer');
      }
    }
  });

  it('admin role: all 7 nav icons enabled (opacity 1, pointer)', () => {
    renderShell();
    // Default is admin
    for (const item of NAV) {
      const icon = document.querySelector(`[title^="${item.cn}"]`) as HTMLElement;
      expect(icon?.style.opacity, `${item.k} should be enabled`).not.toBe('0.3');
      expect(icon?.style.cursor, `${item.k} should be pointer`).toBe('pointer');
    }
  });

  it('employee role: chat/flow/live/ops enabled, explore/audit/plugins disabled', () => {
    renderShell();
    const employeeBtn = screen.getByText('员工');
    fireEvent.click(employeeBtn);

    const allowedKeys = ['chat', 'flow', 'live', 'ops'];
    const disabledKeys = ['explore', 'audit', 'plugins'];

    for (const item of NAV) {
      const icon = document.querySelector(`[title^="${item.cn}"]`) as HTMLElement;
      if (disabledKeys.includes(item.k)) {
        expect(icon?.style.opacity, `${item.k} should be disabled`).toBe('0.3');
      } else if (allowedKeys.includes(item.k)) {
        expect(icon?.style.opacity, `${item.k} should be enabled`).not.toBe('0.3');
      }
    }
  });
});
