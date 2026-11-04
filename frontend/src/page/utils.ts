import type { HistoryRow, Invoice, InvoiceItem } from '../api'

export const STATUS_TITLES: Record<HistoryRow['status'], string> = {
  success: 'Hoàn tất',
  duplicate: 'Trùng hóa đơn',
  processing: 'Đang xử lý',
  failed: 'Lỗi xử lý',
  cancelled: 'Đã hủy',
}

export const ACCOUNTING_TITLES: Record<Invoice['accounting_status'], string> = {
  pending: 'Chờ xác nhận',
  confirmed: 'Đã xác nhận',
  rejected: 'Từ chối',
}

export const UPLOAD_STEPS = [
  'Tải tệp lên khu vực lưu trữ an toàn của tài khoản',
  'Chuyển đổi PDF thành ảnh và chạy nhận dạng chữ OCR',
  'Trích xuất thông tin, kiểm tra logic số học và lưu kết quả',
]

export function formatCurrency(value: number | null | undefined): string {
  return value == null
    ? '—'
    : `${new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 }).format(value)} đ`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = parseDate(value)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

export function parseDate(value: string): Date {
  const vietnameseDate = value.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/)
  if (vietnameseDate) {
    return new Date(Number(vietnameseDate[3]), Number(vietnameseDate[2]) - 1, Number(vietnameseDate[1]))
  }
  return new Date(value)
}

export function invoiceItems(invoice: Invoice): InvoiceItem[] {
  if (Array.isArray(invoice.danh_sach_mat_hang)) return invoice.danh_sach_mat_hang
  if (typeof invoice.danh_sach_mat_hang === 'string') {
    try {
      const parsed: unknown = JSON.parse(invoice.danh_sach_mat_hang)
      return Array.isArray(parsed) ? parsed as InvoiceItem[] : []
    } catch {
      return []
    }
  }
  return []
}
