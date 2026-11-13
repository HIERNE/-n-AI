import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiRequest, cancelJob, getErrorMessage, retryJob, type HistoryRow, type User } from '../api'
import { ConfirmDialog, EmptyState, MetricCard, PageHeading, StatusBadge, type Notice } from './shared'
import { formatCurrency, formatDate, STATUS_TITLES } from './utils'

export function ElapsedTimer({ startTime }: { startTime: string | null | undefined }) {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    if (!startTime) return
    const startMs = new Date(startTime).getTime()
    if (isNaN(startMs)) return

    const tick = () => {
      const diffSec = Math.max(0, Math.floor((Date.now() - startMs) / 1000))
      setSeconds(diffSec)
    }
    tick()
    const timer = setInterval(tick, 1000)
    return () => clearInterval(timer)
  }, [startTime])

  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  const formatted = mins > 0 ? `${mins}m ${String(secs).padStart(2, '0')}s` : `${secs}s`
  const isOverTime = seconds >= 90
  const isWarning = seconds >= 45

  return (
    <span
      className={`elapsed-timer ${isOverTime ? 'danger' : isWarning ? 'warning' : ''}`}
      title={isOverTime ? 'Thời gian chạy đã hơn 1.5 phút. Bạn có thể bấm Hủy để khởi động lại.' : 'Thời gian đã xử lý'}
    >
      ⏱ {formatted}
    </span>
  )
}

export function HistoryTable({
  rows,
  showUploader,
  onRetry,
  onCancel,
}: {
  rows: HistoryRow[]
  showUploader: boolean
  onRetry?: (jobId: number) => Promise<void>
  onCancel?: (jobId: number) => Promise<void>
}) {
  const [expandedErrors, setExpandedErrors] = useState<Record<number, boolean>>({})
  const [loadingJobId, setLoadingJobId] = useState<number | null>(null)
  const [actionType, setActionType] = useState<'retry' | 'cancel' | null>(null)

  const handleAction = async (jobId: number, type: 'retry' | 'cancel') => {
    setLoadingJobId(jobId)
    setActionType(type)
    try {
      if (type === 'retry' && onRetry) {
        await onRetry(jobId)
      } else if (type === 'cancel' && onCancel) {
        await onCancel(jobId)
      }
    } finally {
      setLoadingJobId(null)
      setActionType(null)
    }
  }

  const toggleError = (jobId: number) => {
    setExpandedErrors((prev) => ({ ...prev, [jobId]: !prev[jobId] }))
  }

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th className="row-idx">#</th>
            <th>Mã hóa đơn</th>
            <th>Tên tệp</th>
            {showUploader && <th>Người tải</th>}
            <th>Nhà cung cấp</th>
            <th>Mã số thuế</th>
            <th>Số HĐ</th>
            <th>Ngày lập</th>
            <th>Tổng thanh toán</th>
            <th>Thời gian tải</th>
            <th>Trạng thái</th>
            <th style={{ textAlign: 'center', minWidth: '130px' }}>Thao tác</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const createdDate = row.created_at ? new Date(row.created_at) : new Date()
            const year = isNaN(createdDate.getFullYear()) ? new Date().getFullYear() : createdDate.getFullYear()
            const invoiceCode = `INV-${year}-${String(row.job_id).padStart(4, '0')}`
            const isProcessing = row.status === 'processing'
            const isFailed = row.status === 'failed'
            const isCancelled = row.status === 'cancelled'
            const hasError = isFailed || isCancelled || Boolean(row.progress_error || row.error_message)
            const isExpanded = Boolean(expandedErrors[row.job_id])
            const isLoading = loadingJobId === row.job_id

            return (
              <tr key={row.job_id} className={isExpanded ? 'row-expanded-parent' : undefined}>
                <td className="row-idx">{index + 1}</td>
                <td><span className="inv-code">{invoiceCode}</span></td>
                <td><span className="file-chip" title={row.file_name || ''}>📄 {row.file_name || `Hóa đơn #${row.job_id}`}</span></td>
                {showUploader && <td><span className="uploader-pill">👤 {row.uploader_full_name || row.uploader_username || '—'}</span></td>}
                <td style={{ maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={row.ten_cong_ty_ban || ''}>
                  {row.ten_cong_ty_ban || '—'}
                </td>
                <td style={{ fontFamily: 'var(--font-mono)', color: '#4F46E5', fontSize: '12px' }}>{row.ma_so_thue_ban || '—'}</td>
                <td style={{ color: '#475569', fontWeight: 600 }}>{row.so_hoa_don || '—'}</td>
                <td className="date-cell">{row.ngay_lap || '—'}</td>
                <td className="money-cell">{formatCurrency(row.tong_thanh_toan)}</td>
                <td className="date-cell">{formatDate(row.created_at)}</td>
                <td>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <StatusBadge status={row.status} />
                    {isProcessing && <ElapsedTimer startTime={row.created_at} />}
                  </div>
                </td>
                <td className="action-cell" style={{ textAlign: 'center' }}>
                  <div className="table-actions-inline">
                    {/* NÚT THỬ LẠI DÀNH CHO HÓA ĐƠN LỖI HOẶC ĐÃ HỦY */}
                    {(isFailed || isCancelled) && onRetry && (
                      <button
                        type="button"
                        className="btn-action-sm btn-retry-action"
                        title="Thử nhận dạng và bóc tách lại hóa đơn này"
                        disabled={isLoading}
                        onClick={() => void handleAction(row.job_id, 'retry')}
                      >
                        {isLoading && actionType === 'retry' ? '⏳...' : '🔄 Thử lại'}
                      </button>
                    )}

                    {/* NÚT HỦY DÀNH CHO HÓA ĐƠN ĐANG XỬ LÝ QUÁ LÂU */}
                    {isProcessing && onCancel && (
                      <button
                        type="button"
                        className="btn-action-sm btn-cancel-action"
                        title="Ngừng xử lý hóa đơn đang chạy lâu"
                        disabled={isLoading}
                        onClick={() => void handleAction(row.job_id, 'cancel')}
                      >
                        {isLoading && actionType === 'cancel' ? '⏳...' : '⏹ Hủy'}
                      </button>
                    )}

                    {/* NÚT XEM CHI TIẾT LỖI */}
                    {hasError && (
                      <button
                        type="button"
                        className={`btn-action-sm btn-error-toggle ${isExpanded ? 'active' : ''}`}
                        title="Xem nguyên nhân chi tiết của lỗi"
                        onClick={() => toggleError(row.job_id)}
                      >
                        {isExpanded ? '▲ Ẩn lỗi' : '⚠️ Chi tiết'}
                      </button>
                    )}

                    {!isProcessing && !isFailed && !isCancelled && row.status === 'success' && (
                      <span className="action-success-mark" title="Hóa đơn đã bóc tách thành công">✓ Xong</span>
                    )}
                    {row.status === 'duplicate' && (
                      <span className="action-dup-mark" title="Tệp đã trùng khớp dữ liệu trước đó">Trùng</span>
                    )}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {/* RENDER KHUNG CHI TIẾT LỖI MỞ RỘNG */}
      {rows.some((r) => expandedErrors[r.job_id]) && (
        <div className="expanded-error-inspector">
          {rows
            .filter((r) => expandedErrors[r.job_id])
            .map((r) => (
              <div key={`err-${r.job_id}`} className="error-inspector-card">
                <div className="error-inspector-head">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="error-inspector-badge">⚠️ Báo cáo lỗi chi tiết</span>
                    <strong>Hóa đơn #{r.job_id} ({r.file_name || 'Không tên'})</strong>
                  </div>
                  <button
                    type="button"
                    className="error-inspector-close"
                    onClick={() => toggleError(r.job_id)}
                    title="Đóng chi tiết"
                  >
                    ✕
                  </button>
                </div>
                <div className="error-inspector-reason">
                  <strong>Nguyên nhân nhận diện:</strong>{' '}
                  <span className="error-reason-highlight">
                    {r.error_reason || 'Lỗi bóc tách nội dung hoặc kết nối mạng dịch vụ AI'}
                  </span>
                </div>
                <div className="error-inspector-body">
                  <div className="error-code-label">Log kỹ thuật phản hồi từ máy chủ:</div>
                  <pre className="error-traceback">
                    {r.progress_error || r.error_message || 'Không có thêm traceback lỗi.'}
                  </pre>
                </div>
                <div className="error-inspector-foot">
                  <span className="error-hint-text">
                    💡 <strong>Gợi ý:</strong> Nếu tiến trình bị nghẽn quá 1.5 phút, hãy bấm nút <strong>"Hủy"</strong> rồi <strong>"Thử lại"</strong> để hệ thống tự động đổi luồng OCR / AI dự phòng.
                  </span>
                  {onRetry && (
                    <button
                      type="button"
                      className="button primary small"
                      onClick={() => void handleAction(r.job_id, 'retry')}
                      disabled={loadingJobId === r.job_id}
                    >
                      {loadingJobId === r.job_id && actionType === 'retry' ? 'Đang gửi...' : '🔄 Thử lại hóa đơn này ngay'}
                    </button>
                  )}
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}

export function HistoryPage({ user, setNotice }: {
  user: User
  setNotice: (notice: Notice) => void
}) {
  const [rows, setRows] = useState<HistoryRow[]>([])
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [cleanupPreview, setCleanupPreview] = useState<{ invoice_count: number; job_count: number } | null>(null)
  const [confirmAction, setConfirmAction] = useState<'delete' | 'cleanup' | null>(null)
  const [error, setError] = useState('')
  const isAdmin = user.role === 'admin'

  const refresh = useCallback(async () => {
    try {
      const result = await apiRequest<{ history: HistoryRow[] }>('/api/history')
      setRows(result.history)
      setError('')
      if (isAdmin) {
        const preview = await apiRequest<typeof cleanupPreview>('/api/admin/history/cleanup-preview')
        setCleanupPreview(preview)
      }
    } catch (reason) { setError(getErrorMessage(reason)) }
  }, [isAdmin])

  useEffect(() => { refresh() }, [refresh])

  // Tự động làm mới khi có ít nhất 1 job đang xử lý
  useEffect(() => {
    const hasProcessing = rows.some((r) => r.status === 'processing')
    if (!hasProcessing) return
    const timer = setInterval(refresh, 2500)
    return () => clearInterval(timer)
  }, [rows, refresh])

  const filtered = useMemo(() => rows.filter((row) => {
    const matchesStatus = statusFilter === 'all' || row.status === statusFilter
    const query = search.trim().toLocaleLowerCase()
    const matchesSearch = !query || [
      row.file_name, row.ten_cong_ty_ban, row.ma_so_thue_ban, row.so_hoa_don,
      row.uploader_full_name, row.uploader_username,
    ].some((value) => value?.toLocaleLowerCase().includes(query))
    return matchesStatus && matchesSearch
  }), [rows, search, statusFilter])

  async function handleRetryJob(jobId: number) {
    try {
      await retryJob(jobId)
      setNotice({ kind: 'success', text: `Đã đưa hóa đơn #${jobId} vào hàng đợi xử lý lại.` })
      await refresh()
    } catch (reason) {
      setNotice({ kind: 'error', text: getErrorMessage(reason) })
    }
  }

  async function handleCancelJob(jobId: number) {
    try {
      await cancelJob(jobId)
      setNotice({ kind: 'success', text: `Đã dừng tiến trình xử lý hóa đơn #${jobId}.` })
      await refresh()
    } catch (reason) {
      setNotice({ kind: 'error', text: getErrorMessage(reason) })
    }
  }

  async function deleteSelected() {
    try {
      const result = await apiRequest<{ job_count: number; invoice_count: number }>('/api/admin/history', {
        method: 'DELETE', body: { job_ids: selectedIds },
      })
      setNotice({ kind: 'success', text: `Đã xóa ${result.job_count} dòng lịch sử và ${result.invoice_count} hóa đơn không còn được tham chiếu.` })
      setSelectedIds([])
      setConfirmAction(null)
      await refresh()
    } catch (reason) { setError(getErrorMessage(reason)) }
  }

  async function cleanDuplicates() {
    try {
      const result = await apiRequest<{ job_count: number; invoice_count: number }>('/api/admin/history/cleanup', {
        method: 'POST', body: { confirm: true },
      })
      setNotice({ kind: 'success', text: `Đã dọn ${result.job_count} lịch sử và ${result.invoice_count} hóa đơn trùng.` })
      setConfirmAction(null)
      await refresh()
    } catch (reason) { setError(getErrorMessage(reason)) }
  }

  const deletableRows = filtered.filter((row) => ['duplicate', 'failed', 'cancelled'].includes(row.status))
  const selectableIds = deletableRows.map((row) => row.job_id)

  return (
    <div className="workspace-content">
      <PageHeading
        eyebrow={isAdmin ? 'ADMIN AUDIT & SYSTEM HISTORY' : 'LỊCH SỬ XỬ LÝ HÓA ĐƠN'}
        title="📋 Lịch sử hóa đơn"
        description={isAdmin ? 'Toàn bộ hóa đơn đã xử lý trong hệ thống, công cụ quản trị dữ liệu và xử lý lại lỗi.' : 'Lịch sử các hóa đơn do tài khoản của bạn xử lý, hỗ trợ thử lại khi lỗi hoặc hủy khi quá lâu.'}
        action={<button className="button subtle" onClick={refresh}>↻ Làm mới</button>}
      />
      {error && <div className="inline-error" role="alert">{error}</div>}
      <div className="metric-grid">
        <MetricCard label="Tổng hóa đơn" value={rows.length} detail="Bản ghi trong hệ thống" tone="blue" icon="📄" />
        <MetricCard label="Hoàn tất" value={rows.filter((row) => row.status === 'success').length} detail="Xử lý thành công" tone="green" icon="✅" />
        <MetricCard label="Đang xử lý / Lỗi" value={`${rows.filter((row) => row.status === 'processing').length} / ${rows.filter((row) => row.status === 'failed' || row.status === 'cancelled').length}`} detail="Cần theo dõi hoặc thử lại" tone="amber" icon="⏳" />
        <MetricCard label="Tổng giá trị" value={formatCurrency(rows.filter((row) => row.status === 'success').reduce((sum, row) => sum + (row.tong_thanh_toan || 0), 0))} detail="Hóa đơn thành công" tone="violet" icon="💰" />
      </div>
      {isAdmin && (
        <section className="workspace-panel admin-tools">
          <div className="panel-heading"><div><h2>⚙️ Công cụ quản trị Admin</h2><p>Chỉ xóa dòng trùng/lỗi; hóa đơn gốc luôn được bảo toàn.</p></div></div>
          <div className="admin-actions">
            <label className="check-inline"><input checked={selectableIds.length > 0 && selectableIds.every((id) => selectedIds.includes(id))} onChange={(event) => setSelectedIds(event.target.checked ? selectableIds : [])} type="checkbox" />Chọn các dòng trùng/lỗi đang hiển thị</label>
            <button className="button danger-outline" disabled={!selectedIds.length} onClick={() => setConfirmAction('delete')}>Xóa {selectedIds.length || ''} dòng đã chọn</button>
            <span className="admin-cleanup-count">Phát hiện trùng: {cleanupPreview?.invoice_count ?? 0} hóa đơn · {cleanupPreview?.job_count ?? 0} dòng lịch sử</span>
            <button className="button subtle" disabled={!cleanupPreview?.invoice_count && !cleanupPreview?.job_count} onClick={() => setConfirmAction('cleanup')}>Dọn dẹp bản ghi trùng</button>
          </div>
          {filtered.some((row) => ['duplicate', 'failed', 'cancelled'].includes(row.status)) && (
            <div className="check-list">
              {deletableRows.map((row) => (
                <label key={row.job_id}><input checked={selectedIds.includes(row.job_id)} onChange={(event) => setSelectedIds((ids) => event.target.checked ? [...ids, row.job_id] : ids.filter((id) => id !== row.job_id))} type="checkbox" /><span>#{row.job_id} · {row.file_name || 'Không tên'} · {STATUS_TITLES[row.status]}</span></label>
              ))}
            </div>
          )}
        </section>
      )}
      <section className="workspace-panel">
        <div className="panel-heading"><div><h2>Danh sách hồ sơ hóa đơn</h2><p>{filtered.length} bản ghi phù hợp.</p></div></div>
        <div className="table-filters">
          <input aria-label="Tìm trong lịch sử" onChange={(event) => setSearch(event.target.value)} placeholder="🔍 Tìm theo mã HĐ, tên tệp, nhà cung cấp, MST, số hóa đơn..." value={search} />
          <select aria-label="Lọc trạng thái" onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}>
            <option value="all">Tất cả trạng thái</option>
            {Object.entries(STATUS_TITLES).map(([status, title]) => <option key={status} value={status}>{title}</option>)}
          </select>
        </div>

        <div className="stat-row">
          <span className="stat-pill" style={{ background: '#EEF2FF', color: '#4F46E5' }}>
            Hiển thị: <strong>{filtered.length}</strong>
          </span>
          <span className="stat-pill" style={{ background: '#DCFCE7', color: '#15803D' }}>
            Hoàn tất: <strong>{filtered.filter(r => r.status === 'success').length}</strong>
          </span>
          <span className="stat-pill" style={{ background: '#FEF3C7', color: '#92400E' }}>
            Trùng: <strong>{filtered.filter(r => r.status === 'duplicate').length}</strong>
          </span>
          <span className="stat-pill" style={{ background: '#DBEAFE', color: '#1E40AF' }}>
            Đang xử lý: <strong>{filtered.filter(r => r.status === 'processing').length}</strong>
          </span>
          <span className="stat-pill" style={{ background: '#FEE2E2', color: '#991B1B' }}>
            Lỗi: <strong>{filtered.filter(r => r.status === 'failed').length}</strong>
          </span>
          <span className="stat-pill" style={{ background: '#F1F5F9', color: '#64748B' }}>
            Đã hủy: <strong>{filtered.filter(r => r.status === 'cancelled').length}</strong>
          </span>
        </div>

        {filtered.length ? (
          <HistoryTable
            rows={filtered}
            showUploader={isAdmin}
            onRetry={handleRetryJob}
            onCancel={handleCancelJob}
          />
        ) : (
          <EmptyState title="Không tìm thấy dữ liệu" description="Thử đổi từ khóa hoặc bộ lọc trạng thái." />
        )}
      </section>
      {confirmAction && (
        <ConfirmDialog
          title={confirmAction === 'delete' ? 'Xóa lịch sử đã chọn?' : 'Dọn dữ liệu hóa đơn trùng?'}
          description={confirmAction === 'delete'
            ? `Bạn xác nhận xóa ${selectedIds.length} dòng lịch sử? Hóa đơn vẫn được giữ nếu còn được job khác sử dụng.`
            : `Tìm thấy ${cleanupPreview?.invoice_count ?? 0} hóa đơn và ${cleanupPreview?.job_count ?? 0} dòng lịch sử trùng. Hệ thống giữ bản gốc tạo sớm nhất.`}
          confirmLabel={confirmAction === 'delete' ? 'Xóa bản ghi' : 'Dọn dữ liệu'}
          onCancel={() => setConfirmAction(null)}
          onConfirm={() => { void (confirmAction === 'delete' ? deleteSelected() : cleanDuplicates()) }}
        />
      )}
    </div>
  )
}
