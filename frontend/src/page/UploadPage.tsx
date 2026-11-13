import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { apiRequest, cancelJob, getErrorMessage, retryJob, type HistoryRow } from '../api'
import { EmptyState, PageHeading, type Notice } from './shared'
import { UPLOAD_STEPS } from './utils'
import { ElapsedTimer, HistoryTable } from './HistoryPage'

export function UploadPage({ setNotice }: {
  setNotice: (notice: Notice) => void
}) {
  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [activeJobId, setActiveJobId] = useState<number | null>(null)
  const [activeFileName, setActiveFileName] = useState('')
  const [history, setHistory] = useState<HistoryRow[]>([])
  const [loadError, setLoadError] = useState('')
  const [cancelling, setCancelling] = useState(false)
  const [retrying, setRetrying] = useState(false)

  const refresh = useCallback(() => {
    apiRequest<{ history: HistoryRow[] }>('/api/history')
      .then(({ history: rows }) => {
        setHistory(rows.slice(0, 8))
        setLoadError('')
      })
      .catch((error: unknown) => setLoadError(getErrorMessage(error)))
  }, [])

  const activeJob = history.find((job) => job.job_id === activeJobId)
  const activeStatus = activeJob?.progress_status ?? activeJob?.status

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    if (activeStatus !== 'processing') return
    const timer = window.setInterval(refresh, 2000)
    return () => window.clearInterval(timer)
  }, [activeJobId, activeStatus, refresh])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!files.length) return
    setUploading(true)
    let uploadedCount = 0
    try {
      for (const file of files) {
        setActiveJobId(null)
        setActiveFileName(file.name)
        const formData = new FormData()
        formData.append('file', file)
        const result = await apiRequest<{ job_id: number; status: string }>('/api/uploads', { body: formData })
        setActiveJobId(result.job_id)
        refresh()
        uploadedCount += 1
        setNotice({
          kind: 'success',
          text: result.status === 'duplicate'
            ? `Đã nhận diện "${file.name}" trùng với hóa đơn đã xử lý.`
            : `Đã nhận "${file.name}" vào hàng đợi OCR & AI.`,
        })
      }
      setFiles([])
      refresh()
    } catch (error) {
      setNotice({
        kind: 'error',
        text: uploadedCount
          ? `Đã gửi ${uploadedCount}/${files.length} tệp. ${getErrorMessage(error)}`
          : getErrorMessage(error),
      })
      refresh()
    } finally {
      setUploading(false)
    }
  }

  async function handleCancelActiveJob() {
    if (!activeJobId) return
    setCancelling(true)
    try {
      await cancelJob(activeJobId)
      setNotice({ kind: 'success', text: `Đã dừng tiến trình xử lý hóa đơn #${activeJobId}. Bạn có thể thử lại bất cứ lúc nào.` })
      refresh()
    } catch (err) {
      setNotice({ kind: 'error', text: getErrorMessage(err) })
    } finally {
      setCancelling(false)
    }
  }

  async function handleRetryActiveJob() {
    if (!activeJobId) return
    setRetrying(true)
    try {
      await retryJob(activeJobId)
      setNotice({ kind: 'success', text: `Đã đưa hóa đơn #${activeJobId} vào hàng đợi xử lý lại.` })
      refresh()
    } catch (err) {
      setNotice({ kind: 'error', text: getErrorMessage(err) })
    } finally {
      setRetrying(false)
    }
  }

  async function handleRetryTableJob(jobId: number) {
    try {
      await retryJob(jobId)
      setNotice({ kind: 'success', text: `Đã đưa hóa đơn #${jobId} vào hàng đợi xử lý lại.` })
      setActiveJobId(jobId)
      refresh()
    } catch (err) {
      setNotice({ kind: 'error', text: getErrorMessage(err) })
    }
  }

  async function handleCancelTableJob(jobId: number) {
    try {
      await cancelJob(jobId)
      setNotice({ kind: 'success', text: `Đã dừng xử lý hóa đơn #${jobId}.` })
      refresh()
    } catch (err) {
      setNotice({ kind: 'error', text: getErrorMessage(err) })
    }
  }

  return (
    <div className="workspace-content">
      <PageHeading
        eyebrow="DOCUMENT PROCESSING & AI PIPELINE"
        title="Tải lên hóa đơn"
        description="Tải PDF hoặc ảnh hóa đơn. Quy trình OCR tiếng Việt siêu tốc và bóc tách AI chạy ngầm với cơ chế thử lại & hủy linh hoạt."
      />

      <div className="upload-layout">
        <section className="workspace-panel upload-panel">
          <form onSubmit={submit}>
            <label className="dropzone">
              <input
                accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                multiple
                onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                type="file"
              />
              <span className="upload-icon">↑</span>
              <strong>Kéo thả tệp hóa đơn vào đây hoặc chọn từ máy</strong>
              <small>Hỗ trợ định dạng PDF, PNG, JPG hoặc JPEG · Tối đa 15 MB mỗi tệp</small>
              <span className="button subtle">Chọn tệp từ máy</span>
            </label>
            {files.length > 0 && (
              <div className="selected-files">
                {files.map((file) => (
                  <div key={`${file.name}:${file.size}`}>
                    <span>📄</span>
                    {file.name}
                    <small>{(file.size / 1024 / 1024).toFixed(1)} MB</small>
                  </div>
                ))}
              </div>
            )}
            <button
              className="button primary full-width"
              disabled={!files.length || uploading}
              type="submit"
              style={{ marginTop: '14px' }}
            >
              {uploading ? 'Đang gửi tệp lên máy chủ...' : `Bắt đầu xử lý${files.length ? ` · ${files.length} tệp` : ''}`}
            </button>
          </form>
          <div className="upload-footnote">
            ⚡ Hệ thống tự động tối ưu ảnh độ phân giải cao và đa luồng CPU để nhận dạng tiếng Việt nhanh chóng trong vòng dưới 90 giây.
          </div>
        </section>

        <section className="workspace-panel upload-help">
          <div className="panel-heading">
            <div>
              <h2>Quy trình xử lý hóa đơn</h2>
              <p>Quy trình 3 bước tự động hóa khép kín</p>
            </div>
          </div>
          {UPLOAD_STEPS.map((step, index) => {
            const stepNumber = index + 1
            const progressStep = activeJob?.progress_step ?? (activeStatus === 'success' ? 3 : activeStatus === 'processing' ? 2 : 0)
            const stepStatus = activeStatus === 'success' || stepNumber < progressStep
              ? 'complete'
              : (activeStatus === 'failed' || activeStatus === 'cancelled') && stepNumber === progressStep
                ? 'failed'
                : activeStatus === 'duplicate'
                  ? (stepNumber === 1 ? 'complete' : 'skipped')
                  : (uploading && !activeJobId && stepNumber === 1) || (activeStatus === 'processing' && stepNumber === Math.max(progressStep, 2))
                    ? 'active'
                    : 'pending'
            return (
              <div className={`process-step ${stepStatus}`} key={step} aria-current={stepStatus === 'active' ? 'step' : undefined}>
                <span>{stepStatus === 'complete' ? '✓' : String(stepNumber).padStart(2, '0')}</span>
                <p>{step}</p>
              </div>
            )
          })}

          {(uploading || activeJob) && (
            <div
              className={`process-progress-message ${
                activeStatus === 'failed' ? 'failed' : activeStatus === 'cancelled' ? 'cancelled' : activeStatus === 'success' ? 'complete' : ''
              }`}
              role="status"
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <strong>{activeFileName || activeJob?.file_name || 'Hóa đơn'}</strong>
                {activeStatus === 'processing' && activeJob && (
                  <ElapsedTimer startTime={activeJob.created_at} />
                )}
              </div>

              <span>
                {activeStatus === 'duplicate'
                  ? activeJob?.progress_message || 'Tệp đã trùng với hóa đơn đã xử lý trước đó.'
                  : activeStatus === 'success'
                    ? 'Xử lý hoàn tất thành công.'
                    : activeStatus === 'cancelled'
                      ? 'Đã dừng xử lý theo yêu cầu của bạn.'
                      : activeStatus === 'failed'
                        ? (activeJob?.error_reason ? `Lỗi: ${activeJob.error_reason}` : 'Xử lý thất bại.')
                        : activeJob?.progress_message || (uploading ? 'Đang tải tệp lên máy chủ.' : 'Đang chờ xử lý.')}
              </span>

              {/* BÁO CHI TIẾT LỖI RÕ RÀNG */}
              {(activeStatus === 'failed' || activeStatus === 'cancelled') && (activeJob?.progress_error || activeJob?.error_message) && (
                <div className="active-error-box">
                  <strong>Chi tiết lỗi:</strong>
                  <code>{activeJob.progress_error || activeJob.error_message}</code>
                </div>
              )}

              {/* NÚT ĐIỀU KHIỂN HỦY / THỬ LẠI TRONG KHUNG TIẾN TRÌNH */}
              <div className="active-job-actions">
                {activeStatus === 'processing' && activeJobId && (
                  <button
                    type="button"
                    className="button danger-outline small"
                    disabled={cancelling}
                    onClick={handleCancelActiveJob}
                    title="Nếu xử lý quá lâu, bấm vào đây để dừng và thử lại"
                  >
                    {cancelling ? 'Đang dừng...' : '⏹ Dừng & bắt đầu lại'}
                  </button>
                )}

                {(activeStatus === 'failed' || activeStatus === 'cancelled') && activeJobId && (
                  <button
                    type="button"
                    className="button primary small"
                    disabled={retrying}
                    onClick={handleRetryActiveJob}
                    title="Thử lại xử lý hóa đơn này"
                  >
                    {retrying ? 'Đang chuẩn bị...' : '🔄 Thử lại hóa đơn này'}
                  </button>
                )}
              </div>
            </div>
          )}

          <div className="soft-note">
            Tệp trùng khớp nội dung hoặc mã số thuế/số hóa đơn sẽ được đối soát tự động để tránh xử lý trùng. Nếu hóa đơn tải lâu hơn 1.5 phút, bạn có thể bấm <strong>"Dừng &amp; bắt đầu lại"</strong> để hệ thống chuyển kênh xử lý.
          </div>
        </section>
      </div>

      <section className="workspace-panel">
        <div className="panel-heading">
          <div>
            <h2>Tiến trình tải lên gần đây</h2>
            <p>Trạng thái cập nhật tự động khi đang xử lý. Bạn có thể bấm Thử lại hoặc Hủy trực tiếp tại bảng.</p>
          </div>
          <button className="button subtle" onClick={refresh}>↻ Làm mới</button>
        </div>
        {loadError && <div className="inline-error" role="alert">{loadError}</div>}
        {history.length ? (
          <HistoryTable
            rows={history}
            showUploader={false}
            onRetry={handleRetryTableJob}
            onCancel={handleCancelTableJob}
          />
        ) : (
          <EmptyState title="Chưa có tệp trong phiên" description="Các hóa đơn đã tải lên sẽ xuất hiện tại đây." />
        )}
      </section>
    </div>
  )
}
