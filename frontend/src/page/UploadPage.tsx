import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { apiRequest, getErrorMessage, type HistoryRow } from '../api'
import { EmptyState, PageHeading, type Notice } from './shared'
import { UPLOAD_STEPS } from './utils'
import { HistoryTable } from './HistoryPage'

export function UploadPage({ setNotice }: {
  setNotice: (notice: Notice) => void
}) {
  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [activeJobId, setActiveJobId] = useState<number | null>(null)
  const [activeFileName, setActiveFileName] = useState('')
  const [history, setHistory] = useState<HistoryRow[]>([])
  const [loadError, setLoadError] = useState('')

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
    const timer = window.setInterval(refresh, 1500)
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
            : `Đã nhận "${file.name}" vào hàng đợi OCR.`,
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

  return (
    <div className="workspace-content">
      <PageHeading eyebrow="DOCUMENT PROCESSING" title="Tải lên hóa đơn" description="Tải PDF hoặc ảnh. Việc OCR và trích xuất AI chạy ngầm trên máy chủ để bạn không bị khóa màn hình." />
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
                {files.map((file) => <div key={`${file.name}:${file.size}`}><span>📄</span>{file.name}<small>{(file.size / 1024 / 1024).toFixed(1)} MB</small></div>)}
              </div>
            )}
            <button className="button primary full-width" disabled={!files.length || uploading} type="submit" style={{ marginTop: '14px' }}>
              {uploading ? 'Đang gửi tệp lên máy chủ...' : `Bắt đầu xử lý${files.length ? ` · ${files.length} tệp` : ''}`}
            </button>
          </form>
          <div className="upload-footnote">Sau khi tải lên, hệ thống sẽ tự động chuyển đổi ảnh, nhận dạng OCR và bóc tách dữ liệu theo schema chuẩn.</div>
        </section>
        <section className="workspace-panel upload-help">
          <div className="panel-heading"><div><h2>Quy trình xử lý hóa đơn</h2><p>Quy trình 3 bước tự động hóa khép kín</p></div></div>
          {UPLOAD_STEPS.map((step, index) => {
            const stepNumber = index + 1
            const progressStep = activeJob?.progress_step ?? (activeStatus === 'success' ? 3 : activeStatus === 'processing' ? 2 : 0)
            const stepStatus = activeStatus === 'success' || stepNumber < progressStep
              ? 'complete'
              : activeStatus === 'failed' && stepNumber === progressStep
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
            <div className={`process-progress-message ${activeStatus === 'failed' ? 'failed' : activeStatus === 'success' ? 'complete' : ''}`} role="status">
              <strong>{activeFileName || activeJob?.file_name || 'Hóa đơn'}</strong>
              <span>
                {activeStatus === 'duplicate'
                  ? activeJob?.progress_message || 'Tệp đã được xử lý trước đó.'
                  : activeStatus === 'success'
                    ? 'Xử lý hoàn tất.'
                    : activeStatus === 'failed'
                      ? 'Xử lý thất bại. Kiểm tra log máy chủ để biết chi tiết.'
                      : activeJob?.progress_message || (uploading ? 'Đang tải tệp lên máy chủ.' : 'Đang chờ xử lý.')}
              </span>
              {activeStatus === 'failed' && activeJob?.progress_error && <small>{activeJob.progress_error}</small>}
            </div>
          )}
          <div className="soft-note">Tệp trùng khớp nội dung hoặc mã số thuế/số hóa đơn sẽ được đối soát tự động để tránh xử lý trùng.</div>
        </section>
      </div>
      <section className="workspace-panel">
        <div className="panel-heading"><div><h2>Tiến trình tải lên gần đây</h2><p>Trạng thái cập nhật tự động khi đang xử lý.</p></div><button className="button subtle" onClick={refresh}>↻ Làm mới</button></div>
        {loadError && <div className="inline-error" role="alert">{loadError}</div>}
        {history.length ? <HistoryTable rows={history} showUploader={false} /> : <EmptyState title="Chưa có tệp trong phiên" description="Các hóa đơn đã tải lên sẽ xuất hiện tại đây." />}
      </section>
    </div>
  )
}
