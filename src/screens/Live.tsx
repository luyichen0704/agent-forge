import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Icon, Tag, Dot, Note, Btn, StatTile } from '../components/kit';
import { useApp } from '../lib/appContext';
import { useMe } from '../features/auth';
import { useSources, useStartExplore, useJob, useExplorationStream } from '../features/sources';
import { streamLabel, kindLabel, explorerLabel, opTitle } from '../lib/labels';
import { shortSourceName, fmtInt } from '../lib/format';

const PHASES = ['全局认知', '深度探索', '操作生成', '能力标注'];

export function LiveMain() {
  const { treeSel, setTreeSel, toast } = useApp();
  const role = useMe().data?.acting_role ?? 'admin';
  const sources = useSources();
  const start = useStartExplore();
  const qc = useQueryClient();

  // Auto-attach to the most recently started job (written by Explore's
  // useStartExplore onSuccess). Subscribe via useQuery so a job started
  // *after* this screen mounts still attaches (cache reads are one-shot).
  const latestJob = useQuery<string | undefined>({
    queryKey: ['job-latest'],
    queryFn: () => undefined,
    enabled: false,
  });
  const [jobId, setJobId] = useState<string | undefined>(latestJob.data ?? undefined);
  const [selSrc, setSelSrc] = useState<string>(''); // the source the admin intends to explore next
  const job = useJob(jobId);
  const events = useExplorationStream(jobId);
  const logRef = useRef<HTMLDivElement>(null);

  const srcList = useMemo(() => sources.data?.items ?? [], [sources.data]);

  // Keep job-latest in sync
  useEffect(() => {
    if (latestJob.data && !jobId) setJobId(latestJob.data);
  }, [latestJob.data, jobId]);

  // Focus the source of the running job as soon as we learn it.
  const jobSourceId = job.data?.source_id;
  useEffect(() => {
    if (jobSourceId && !selSrc) setSelSrc(jobSourceId);
  }, [jobSourceId, selSrc]);

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [events]);

  // when exploration finishes, newly-discovered operations/sources are ready → refresh
  useEffect(() => {
    if (events.some((e) => e.type === 'done')) {
      qc.invalidateQueries({ queryKey: ['operations'] });
      qc.invalidateQueries({ queryKey: ['sources'] });
      if (jobId) qc.invalidateQueries({ queryKey: ['job', jobId] });
    }
  }, [events, qc, jobId]);

  const activePhase = treeSel > 0 ? treeSel : null; // 1-indexed

  // The source in focus: the running job's source wins; otherwise the admin's pick; otherwise first.
  const focusId = jobSourceId ?? selSrc ?? srcList[0]?.id;
  const src = srcList.find((s) => s.id === focusId) ?? srcList[0];
  const phase = job.data?.phase ?? 0;
  const progress = job.data?.progress ?? 0;
  const running = jobId != null && job.data?.status !== 'done' && job.data?.status !== 'error';

  // Live discovery counters from the event stream.
  const opCount = events.filter((e) => e.type === 'op').length;
  const ruleCount = events.filter((e) => e.type === 'rule').length;
  const doneEv = events.find((e) => e.type === 'done');
  const discovered = doneEv ? Number(doneEv.payload.operations ?? opCount) : opCount;

  function begin() {
    const target = srcList.find((s) => s.id === (selSrc || focusId));
    if (!target) return;
    start.mutate(target.id, {
      onSuccess: (r) => {
        setJobId(r.job_id);
        setSelSrc(target.id);
        qc.setQueryData(['job-latest'], r.job_id);
        toast(`已开始探索「${shortSourceName(target.name)}」`, 'info');
      },
      onError: (e) => toast((e as Error).message, 'warn'),
    });
  }

  const srcShort = src ? shortSourceName(src.name) : '—';

  return (
    <div className="col gap14 fill scroll" style={{ padding: 16 }}>
      {/* focus + control bar */}
      <div className="row between vcenter wrap gap10">
        <div className="row vcenter gap8" style={{ minWidth: 0 }}>
          <Icon n="pulse" s={15} c="var(--accent)" />
          {role === 'admin' && srcList.length > 0 ? (
            <select className="sel" aria-label="选择要探索的系统" value={selSrc || focusId || ''}
              onChange={(e) => setSelSrc(e.target.value)} disabled={running} style={{ maxWidth: 260 }}>
              {srcList.map((s) => (
                <option key={s.id} value={s.id}>{shortSourceName(s.name)}</option>
              ))}
            </select>
          ) : (
            <span className="b sm">{srcShort}</span>
          )}
          {src && <span className="sm muted">· {explorerLabel(src.connector_kind)}</span>}
        </div>
        <div className="row vcenter gap10">
          {jobId && <>
            <span className="sm muted tnum">{progress}%</span>
            <div className="prog" style={{ width: 140 }}><i style={{ width: `${progress}%` }} /></div>
          </>}
          {role === 'admin' && <Btn sz="sm" k="pri" ic="play" disabled={start.isPending || running || !src} onClick={begin}>
            {jobId ? '重新探索' : '开始探索'}</Btn>}
        </div>
      </div>

      {/* live discovery stats */}
      <div className="stat-grid">
        <StatTile label="当前阶段" value={<span className="tnum">{Math.min(Math.max(phase, jobId ? 1 : 0), 4)}<span className="muted" style={{ fontSize: 13 }}> / 4</span></span>}
          sub={jobId ? PHASES[Math.min(Math.max(phase - 1, 0), 3)] : '尚未开始'} accent="var(--accent-ink)" icon={<Icon n="layers" s={15} c="var(--ink-4)" />} />
        <StatTile label="已发现操作" value={<span className="tnum">{fmtInt(discovered)}</span>}
          sub={running ? '探索进行中…' : doneEv ? '本次探索完成' : '等待开始'} accent="var(--cap-data)" icon={<Icon n="bolt" s={15} c="var(--ink-4)" />} />
        <StatTile label="业务规则" value={<span className="tnum">{fmtInt(ruleCount)}</span>}
          sub="从数据源提炼" accent="var(--cap-parsed)" icon={<Icon n="doc" s={15} c="var(--ink-4)" />} />
        <StatTile label="探索状态" value={running ? '进行中' : doneEv ? '已完成' : '待命'}
          sub={src ? srcShort : ''} accent={running ? 'var(--cap-parsed)' : doneEv ? 'var(--cap-trusted)' : 'var(--ink-3)'}
          icon={<Dot k={running ? 'wait' : doneEv ? 'ok' : 'off'} />} />
      </div>

      <div className="row gap14 wrap">
        <div className="card col gap10" style={{ width: 230, padding: 14 }}>
          <span className="eyebrow">探索阶段</span>
          {PHASES.map((label, i) => {
            const phaseNum = i + 1;
            const st = phase > phaseNum || job.data?.status === 'done' ? 'done' : phase === phaseNum ? 'now' : 'todo';
            const isHighlighted = activePhase === phaseNum;
            return (
              <div key={i}
                className="row vcenter gap8"
                style={{
                  fontSize: 12.5,
                  color: st === 'todo' ? 'var(--ink-4)' : 'var(--ink-2)',
                  cursor: 'pointer',
                  borderRadius: 5,
                  padding: '2px 4px',
                  background: isHighlighted ? 'var(--accent-soft)' : undefined,
                  border: isHighlighted ? '1px solid var(--accent-line)' : '1px solid transparent',
                }}
                role="button"
                tabIndex={0}
                onClick={() => setTreeSel(isHighlighted ? 0 : phaseNum)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTreeSel(isHighlighted ? 0 : phaseNum); } }}
              >
                <Dot k={st === 'done' ? 'ok' : st === 'now' ? 'wait' : 'off'} />
                <span className="b">阶段 {phaseNum}</span><span className="fill">{label}</span>
                {st === 'done' && <Icon n="check" s={13} c="var(--cap-trusted)" />}
                {st === 'now' && <span className="xs" style={{ color: 'var(--accent-ink)' }}>进行中</span>}
              </div>
            );
          })}
        </div>
        <div className="card col fill gap8" style={{ padding: 14, minWidth: 280 }}>
          <div className="row between vcenter">
            <span className="eyebrow">实时日志 · {srcShort}</span>
            {jobId && job.data?.status !== 'done' && <span className="row vcenter gap5 xs muted"><Dot k="wait" /> 进行中</span>}
          </div>
          <div ref={logRef} className="code" style={{ maxHeight: 320, minHeight: 120 }} data-tour="live-log">
            {!jobId && <span className="c">{'// 选择系统后点击「开始探索」，系统会自动读取数据源并发现可用操作'}</span>}
            {events
              .filter((e) => activePhase == null || e.type !== 'phase' || (e.payload.phase as number) === activePhase)
              .map((e, i) => (
                <div key={i}>
                  <span className="c">{`[${streamLabel(e.type)}] `}</span>
                  <span>{e.type === 'op' ? `${String(e.payload.desc || '').trim() || opTitle({ op_key: String(e.payload.key) })}（${kindLabel(String(e.payload.kind))}）`
                    : e.type === 'phase' ? `阶段 ${e.payload.phase} · ${e.payload.label}`
                    : e.type === 'rule' ? `${e.payload.text}`
                    : e.type === 'done' ? `共发现 ${e.payload.operations} 个操作`
                    : JSON.stringify(e.payload)}</span>
                </div>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function LiveAside() {
  const sources = useSources();
  const items = sources.data?.items ?? [];
  const running = items.filter((s) => s.status === 'running').length;
  return (
    <div className="col fill">
      <div style={{ padding: 14, borderBottom: '1px solid var(--line-2)' }}><span className="h3">探索概览</span></div>
      <div className="col gap12 fill scroll" style={{ padding: 14 }}>
        <div className="row between"><span className="sm muted">已接入系统</span><span className="b tnum">{items.length}</span></div>
        <div className="row between"><span className="sm muted">探索中</span><Tag k="parsed">{running}</Tag></div>
        <div className="row between"><span className="sm muted">已就绪</span><Tag k="trusted">{items.filter((s) => s.status === 'connected').length}</Tag></div>
        <div className="divln" />
        <Note ink>系统会自动读取数据源、发现可用操作并登记到操作清单（写操作需审核后启用）。</Note>
      </div>
    </div>
  );
}
