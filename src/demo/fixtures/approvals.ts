/** Demo approval request fixtures */
import type { ApprovalRequest } from '../../api/types';

/** Seed pending dual-approval request (e.g., from a previous scenario B run) */
export const SEED_APPROVAL: ApprovalRequest = {
  id: 'appr-seed-001',
  trace_id: null,
  target_type: 'plan',
  target_id: 'plan-seed-001',
  confirm_level: 'dual',
  status: 'pending',
  required_votes: 2,
  approve_votes: 0,
  votes: [],
};
