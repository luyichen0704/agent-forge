/** Deterministic fake SHA-256 hash chain for demo audit events */

/** Simple deterministic hash — not cryptographically secure, only for demo */
function fakeHash(input: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  // Expand to 64 hex chars by remixing each round. (A self-XOR like
  // h ^ (h >> 0) zeroes the first block, which the audit UI displays.)
  let result = '';
  let x = h;
  for (let i = 0; i < 8; i++) {
    x = (x ^ (x >>> 13)) >>> 0;
    x = (Math.imul(x, 0x5bd1e995) + i) >>> 0;
    result += x.toString(16).padStart(8, '0');
  }
  return result.substring(0, 64);
}

/** Build a hash chain: each entry hashes prevHash + event + JSON(payload) */
export function buildHashChain(
  events: Array<{ event: string; payload: Record<string, unknown> }>
): Array<{ hash: string; prev_hash: string }> {
  const GENESIS = '0000000000000000000000000000000000000000000000000000000000000000';
  const result: Array<{ hash: string; prev_hash: string }> = [];
  let prevHash = GENESIS;

  for (const ev of events) {
    const input = prevHash + ev.event + JSON.stringify(ev.payload);
    const hash = fakeHash(input);
    result.push({ hash, prev_hash: prevHash });
    prevHash = hash;
  }
  return result;
}

/** Generate a deterministic fake UUID-like ID from a seed string */
export function fakeId(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = ((h << 5) - h + seed.charCodeAt(i)) | 0;
  }
  const hex = Math.abs(h).toString(16).padStart(8, '0');
  return `${hex.slice(0, 8)}-${hex.slice(0, 4)}-4${hex.slice(1, 4)}-a${hex.slice(2, 5)}-${hex.slice(0, 12).padEnd(12, '0')}`;
}
