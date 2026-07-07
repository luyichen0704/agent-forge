/* Client-side memory of which system a chat session is scoped to, plus when the
 * user created it. The backend's GET /chat/sessions returns only {id, title};
 * source_id is returned by POST create but not re-listed. We record the user's
 * own selection at creation time so the session list can show a system badge and
 * relative time. This is the user's real choice (not mock data), persisted in
 * localStorage so it survives reloads. */

export interface SessionMeta { sourceId: string | null; sourceName: string | null; createdAt: number }

const KEY = 'agentforge.sessionMeta';

type Store = Record<string, SessionMeta>;

function read(): Store {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Store) : {};
  } catch {
    return {};
  }
}

function write(s: Store): void {
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* ignore quota */ }
}

export function setSessionMeta(id: string, meta: SessionMeta): void {
  const s = read();
  s[id] = meta;
  write(s);
}

export function getSessionMeta(id: string): SessionMeta | undefined {
  return read()[id];
}

export function getAllSessionMeta(): Store {
  return read();
}
