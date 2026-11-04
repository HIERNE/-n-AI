import { useCallback, useEffect, useState } from 'react'
import { apiRequest, getErrorMessage, type Job, type User } from '../api'
import { EmptyState, MetricCard, PageHeading, StatusBadge, type Screen } from './shared'
import { formatDate } from './utils'

export function DashboardPage({ user, navigate }: {
  user: User
  navigate: (screen: Screen) => void
}) {
  const [dashboard, setDashboard] = useState<{
    invoice_count: number
    confirmed_count: number
    job_counts: Record<string, number>
    recent_jobs: Job[]
  } | null>(null)
  const [error, setError] = useState('')

  const refresh = useCallback(() => {
    apiRequest<typeof dashboard>('/api/dashboard')
      .then(setDashboard)
      .catch((reason: unknown) => setError(getErrorMessage(reason)))
  }, [])
  useEffect(() => { refresh() }, [refresh])

  return (
    <div className="workspace-content">
      <PageHeading
        eyebrow="INVOICE PRO · WORKSPACE"
        title={`Xin chào, ${user.full_name || user.username}`}
        description="Theo dõi tiến trình xử lý, kiểm toán số học và quản lý toàn diện các hóa đơn doanh nghiệp."
        action={<button className="button primary" onClick={() => navigate('upload')}>＋ Tải hóa đơn</button>}
      />
      {error && <div className="inline-error" role="alert">{error}</div>}
      <div className="metric-grid">
        <MetricCard label="Tổng hóa đơn" value={dashboard?.invoice_count ?? '—'} detail="Hóa đơn trong tài khoản" tone="blue" icon="📄" />
        <MetricCard label="Đã xác nhận" value={dashboard?.confirmed_count ?? '—'} detail="Sẵn sàng cho kế toán" tone="green" icon="✅" />
        <MetricCard label="Đang xử lý" value={dashboard?.job_counts.processing ?? '—'} detail="OCR và bóc tách AI" tone="amber" icon="⏳" />
        <MetricCard label="Cần kiểm tra" value={dashboard?.job_counts.failed ?? '—'} detail="Tệp lỗi hoặc sai lệch" tone="violet" icon="⚠️" />
      </div>
      <section className="workspace-panel">
        <div className="panel-heading">
          <div><h2>Tiến trình xử lý gần đây</h2><p>Cập nhật trạng thái nhận dạng hóa đơn mới nhất.</p></div>
          <button className="button subtle" onClick={() => navigate('history')}>Xem toàn bộ lịch sử →</button>
        </div>
        {dashboard?.recent_jobs.length ? (
          <div className="job-list">
            {dashboard.recent_jobs.map((job) => (
              <div className="job-row" key={job.id}>
                <span className="document-icon">▤</span>
                <div className="job-info"><strong>{job.file_name || `Hóa đơn #${job.id}`}</strong><small>{formatDate(job.created_at)}</small></div>
                <StatusBadge status={job.status} />
              </div>
            ))}
          </div>
        ) : <EmptyState title="Chưa có hóa đơn nào" description="Tải lên tệp PDF hoặc ảnh hóa đơn để bắt đầu quy trình bóc tách tự động." action={<button className="button primary" onClick={() => navigate('upload')}>Tải hóa đơn đầu tiên</button>} />}
      </section>
    </div>
  )
}
