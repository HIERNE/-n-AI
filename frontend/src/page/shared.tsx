import type { HistoryRow } from '../api'
import { STATUS_TITLES } from './utils'

export type Screen = 'dashboard' | 'upload' | 'history' | 'extract' | 'accounting' | 'reports'
export type Notice = { kind: 'success' | 'error'; text: string }

export function ErrorNotice({ notice, onDismiss }: { notice: Notice | null; onDismiss: () => void }) {
  if (!notice) return null
  return (
    <div className={`workspace-notice ${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>
      <span>{notice.kind === 'success' ? '✓' : '!'}</span>
      {notice.text}
      <button aria-label="Đóng thông báo" onClick={onDismiss}>×</button>
    </div>
  )
}

export function PageHeading({ eyebrow, title, description, action }: {
  eyebrow: string
  title: string
  description: string
  action?: React.ReactNode
}) {
  const now = new Date()
  const currentPeriod = `T${String(now.getMonth() + 1).padStart(2, '0')}/${now.getFullYear()}`

  return (
    <div className="page-header">
      <div className="page-header-left">
        <div className="page-header-badge">
          <span className="badge-dot" />
          {eyebrow}
        </div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="page-header-right">
        <div className="header-period-pill">
          <span>KỲ XỬ LÝ</span>
          {currentPeriod}
        </div>
        {action}
      </div>
    </div>
  )
}

export function MetricCard({ label, value, detail, tone, icon }: {
  label: string
  value: string | number
  detail: string
  tone: 'blue' | 'green' | 'amber' | 'violet'
  icon?: string
}) {
  return (
    <article className={`metric-card ${tone}`} data-icon={icon}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-sub">{detail}</div>
    </article>
  )
}

export function StatusBadge({ status }: { status: HistoryRow['status'] }) {
  const isPulse = status === 'processing'
  return (
    <span className={`status-badge status-${status}`}>
      <span className={`badge-dot ${isPulse ? 'pulse' : ''}`} />
      {STATUS_TITLES[status] ?? status}
    </span>
  )
}

export function EmptyState({ title, description, action }: {
  title: string
  description: string
  action?: React.ReactNode
}) {
  return <div className="empty-state"><span>▤</span><strong>{title}</strong><p>{description}</p>{action}</div>
}

export function ConfirmDialog({ title, description, confirmLabel, onCancel, onConfirm }: {
  title: string
  description: string
  confirmLabel: string
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div className="dialog-backdrop" onClick={onCancel}>
      <section aria-labelledby="confirm-title" aria-modal="true" className="confirm-dialog" onClick={(event) => event.stopPropagation()} role="dialog">
        <button aria-label="Đóng" className="dialog-close" onClick={onCancel}>×</button>
        <span className="confirm-icon">!</span>
        <h2 id="confirm-title">{title}</h2><p>{description}</p>
        <div><button className="button subtle" onClick={onCancel}>Hủy</button><button className="button danger" onClick={onConfirm}>{confirmLabel}</button></div>
      </section>
    </div>
  )
}
