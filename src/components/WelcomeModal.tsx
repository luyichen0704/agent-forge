import { Fragment } from 'react';
import { markWelcomeSeen } from '../tour/engine';
import { useTour } from '../tour/TourProvider';
import { Icon } from './kit/Icon';
import { WORKFLOW_STEPS, STEP_BADGES } from '../lib/config/navDesc';

interface WelcomeModalProps {
  onClose: () => void;
}

export function WelcomeModal({ onClose }: WelcomeModalProps) {
  const { start } = useTour();

  function handleStartTour() {
    markWelcomeSeen();
    onClose();
    start();
  }

  function handleSkip() {
    markWelcomeSeen();
    onClose();
  }

  return (
    <div className="tour-welcome-backdrop" role="dialog" aria-label="欢迎使用 agent·forge" onClick={(e) => { if (e.target === e.currentTarget) handleSkip(); }}>
      <div className="tour-welcome" onClick={(e) => e.stopPropagation()}>
        <div className="tw-header">
          <div className="row vcenter gap10" style={{ marginBottom: 10 }}>
            <span className="mk" style={{ width: 28, height: 28, borderRadius: 8, background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Icon n="hex" s={14} c="#fff" />
            </span>
            <span className="h2">agent·forge</span>
          </div>
          <p className="sm muted2" style={{ margin: 0, lineHeight: 1.55 }}>
            让 AI 用自然语言操作企业系统——每一次改动都可控、可审、可回滚。
          </p>
        </div>

        <div className="tw-body">
          {/* Three feature cards */}
          <div className="tw-cards">
            <div className="tw-card">
              <div className="row vcenter gap6">
                <Icon n="chat" s={16} c="var(--accent)" />
                <span className="b sm">它是什么</span>
              </div>
              <p className="xs muted" style={{ margin: 0, lineHeight: 1.5 }}>
                AI 企业治理控制台：用自然语言操作任意业务系统，同时保持完整的可审计性与可控性。
              </p>
            </div>
            <div className="tw-card">
              <div className="row vcenter gap6">
                <Icon n="bolt" s={16} c="var(--accent)" />
                <span className="b sm">怎么用</span>
              </div>
              <p className="xs muted" style={{ margin: 0, lineHeight: 1.5 }}>
                三步走：① 接入数据源 → ② 用对话下达指令并确认执行 → ③ 在审计链中查看与回滚。
              </p>
            </div>
            <div className="tw-card">
              <div className="row vcenter gap6">
                <Icon n="shield" s={16} c="var(--accent)" />
                <span className="b sm">核心保障</span>
              </div>
              <p className="xs muted" style={{ margin: 0, lineHeight: 1.5 }}>
                三重保障：标注数据来源防止被滥用、写操作必须人工审核、操作记录完整不可篡改。
              </p>
            </div>
          </div>

          {/* Workflow strip */}
          <div>
            <div className="eyebrow" style={{ marginBottom: 8 }}>工作流 · 三步完成一次业务操作</div>
            <div className="tw-workflow">
              {WORKFLOW_STEPS.map((label, i) => (
                <Fragment key={label}>
                  <div className="tw-step-pill">
                    <span style={{ color: 'var(--accent-ink)', fontWeight: 700, fontSize: 13 }}>
                      {STEP_BADGES[(i + 1) as 1 | 2 | 3]}
                    </span>
                    {label}
                  </div>
                  {i < WORKFLOW_STEPS.length - 1 && (
                    <span className="tw-arrow">→</span>
                  )}
                </Fragment>
              ))}
            </div>
          </div>
        </div>

        <div className="tw-foot">
          <button className="btn ghost sm" onClick={handleSkip}>自己先逛逛</button>
          <button className="btn pri" onClick={handleStartTour}>
            <Icon n="play" s={14} c="#fff" />
            开始交互教程（约 3 分钟）
          </button>
        </div>
      </div>
    </div>
  );
}
