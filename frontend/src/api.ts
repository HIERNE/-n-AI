export type User = {
  id: number
  username: string
  full_name: string | null
  email: string | null
  role: 'admin' | 'user'
}

export type InvoiceItem = {
  ten_hang?: string
  so_luong?: number | string
  don_gia?: number | string
  thanh_tien?: number | string
}

export type Invoice = {
  id: number
  source_image: string | null
  ma_so_thue_ban: string | null
  ten_cong_ty_ban: string | null
  so_hoa_don: string | null
  ma_so_thue_mua: string | null
  ten_cong_ty_mua: string | null
  ngay_lap: string | null
  danh_sach_mat_hang: InvoiceItem[] | string | null
  tong_tien_hang: number | null
  thue_suat_vat: string | null
  tien_thue_vat: number | null
  tong_thanh_toan: number | null
  accounting_status: 'pending' | 'confirmed' | 'rejected'
  payment_status: 'paid' | 'unpaid'
  created_at: string | null
  uploader_username?: string | null
  uploader_full_name?: string | null
}

export type HistoryRow = {
  job_id: number
  file_name: string | null
  source_image: string | null
  status: 'success' | 'duplicate' | 'processing' | 'failed' | 'cancelled'
  progress_step?: number
  progress_status?: 'success' | 'duplicate' | 'processing' | 'failed' | 'cancelled'
  progress_message?: string
  progress_error?: string | null
  error_message?: string | null
  error_reason?: string | null
  created_at: string | null
  ma_so_thue_ban: string | null
  ten_cong_ty_ban: string | null
  so_hoa_don: string | null
  ngay_lap: string | null
  tong_thanh_toan: number | null
  uploader_username?: string | null
  uploader_full_name?: string | null
}

export type Job = {
  id: number
  file_name: string | null
  status: HistoryRow['status']
  created_at: string | null
  invoice_id: number | null
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function apiRequest<T>(
  path: string,
  options: { method?: string; body?: BodyInit | object; headers?: HeadersInit } = {},
): Promise<T> {
  const { body, headers, method = body === undefined ? 'GET' : 'POST' } = options
  const requestHeaders = new Headers(headers)
  let requestBody: BodyInit | undefined
  if (body instanceof FormData || body instanceof Blob || typeof body === 'string') {
    requestBody = body
  } else if (body !== undefined) {
    requestHeaders.set('Content-Type', 'application/json')
    requestBody = JSON.stringify(body)
  }

  const response = await fetch(path, {
    method,
    credentials: 'include',
    headers: requestHeaders,
    body: requestBody,
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new ApiError(
      payload.detail ?? 'Không thể kết nối tới máy chủ. Vui lòng thử lại.',
      response.status,
    )
  }
  if (response.status === 204) return undefined as T
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) return response.json() as Promise<T>
  return response as T
}

export type AccountingExportOptions = {
  paymentStatus?: string
  month?: number | 'all'
  year?: number | 'all'
}

export async function downloadAccountingExcel(
  optionsOrStatus?: string | AccountingExportOptions,
): Promise<void> {
  const options: AccountingExportOptions =
    typeof optionsOrStatus === 'string'
      ? { paymentStatus: optionsOrStatus }
      : optionsOrStatus ?? {}

  const params = new URLSearchParams()
  if (options.paymentStatus && options.paymentStatus !== 'all') {
    params.set('payment_status', options.paymentStatus)
  }
  if (options.month !== undefined && options.month !== 'all') {
    params.set('month', String(options.month))
  }
  if (options.year !== undefined && options.year !== 'all') {
    params.set('year', String(options.year))
  }

  const query = params.toString() ? `?${params.toString()}` : ''
  const response = await apiRequest<Response>(`/api/accounting/export${query}`)
  const blob = await response.blob()

  const disposition = response.headers.get('content-disposition') ?? ''
  const filenameMatch = disposition.match(/filename="?([^";]+)"?/)
  const filename = filenameMatch ? filenameMatch[1] : 'hach_toan_hoa_don.xlsx'

  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export async function retryJob(jobId: number): Promise<{ job_id: number; status: string }> {
  return apiRequest<{ job_id: number; status: string }>(`/api/jobs/${jobId}/retry`, { method: 'POST' })
}

export async function cancelJob(jobId: number): Promise<{ job_id: number; status: string; message: string }> {
  return apiRequest<{ job_id: number; status: string; message: string }>(`/api/jobs/${jobId}/cancel`, { method: 'POST' })
}

export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Đã xảy ra lỗi. Vui lòng thử lại.'
}
