import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AppProvider } from '../lib/appContext';
import { Shell } from '../components/Shell';
import { OPS } from '../lib/data';

function renderWithShell() {
  return render(
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}

function navigateToOps() {
  const opsIcon = document.querySelector('[title^="操作管理"]') as HTMLElement;
  fireEvent.click(opsIcon);
}

describe('OpsMain — role-based row filtering', () => {
  it('admin sees all 6 ops rows', () => {
    renderWithShell();
    navigateToOps();
    // All 6 operations should be visible — use getAllByText since name appears in table + aside
    for (const op of OPS) {
      const elements = screen.getAllByText(op.name);
      expect(elements.length).toBeGreaterThanOrEqual(1);
    }
  });

  it('employee: hr.salary_set and user.ban are hidden', () => {
    renderWithShell();
    navigateToOps();

    // Switch to employee
    const employeeBtn = screen.getByText('员工');
    fireEvent.click(employeeBtn);

    // hr.salary_set and user.ban should not be visible in the table
    expect(screen.queryByText('hr.salary_set')).toBeNull();
    expect(screen.queryByText('user.ban')).toBeNull();

    // But allowed ops should be visible
    const orderQuery = screen.getAllByText('order.query');
    expect(orderQuery.length).toBeGreaterThanOrEqual(1);
  });

  it('selecting hr.salary_set as admin shows dual-approval panel', () => {
    renderWithShell();
    navigateToOps();

    // Admin is default role. Click on hr.salary_set row in the table
    const salaryCell = screen.getAllByText('hr.salary_set')[0];
    fireEvent.click(salaryCell);

    // Dual approval panel should appear
    expect(screen.getByText(/dual approval/i)).toBeInTheDocument();
    expect(screen.getByText(/待双人确认/)).toBeInTheDocument();
  });

  it('data: OPS data correctly marks hr.salary_set as admin-only', () => {
    const salaryOp = OPS.find(o => o.name === 'hr.salary_set');
    const banOp = OPS.find(o => o.name === 'user.ban');
    expect(salaryOp?.roles).toEqual(['admin']);
    expect(banOp?.roles).toContain('admin');
    expect(banOp?.roles).not.toContain('customer');
    expect(banOp?.roles).not.toContain('employee');
  });

  it('approving a pending op flips its status to active', () => {
    renderWithShell();
    navigateToOps();

    // Select a pending op (order.cancel is default opsSel and pending)
    fireEvent.click(screen.getAllByText('order.cancel')[0]);
    // Aside shows the 批准激活 button for pending op as admin
    const approve = screen.getByText('批准激活');
    fireEvent.click(approve);
    // After approval the pending action is gone and active confirmation shows
    expect(screen.queryByText('批准激活')).toBeNull();
    expect(screen.getByText(/已激活/)).toBeInTheDocument();
  });

  it('batch approve clears all pending rows', () => {
    renderWithShell();
    navigateToOps();
    // There are pending ops initially
    expect(screen.getAllByText('pending').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText('批量批准'));
    // No pending status left in the (admin) visible table
    expect(screen.queryByText('pending')).toBeNull();
  });

  it('clicking a row changes opsSel and updates aside', () => {
    renderWithShell();
    navigateToOps();

    // Default opsSel is 'order.cancel'. Click 'refund.expedite' row
    const cells = screen.getAllByText('refund.expedite');
    fireEvent.click(cells[0]);

    // Aside should now show refund.expedite
    const allRefund = screen.getAllByText('refund.expedite');
    expect(allRefund.length).toBeGreaterThanOrEqual(2); // table cell + aside h3
  });
});
