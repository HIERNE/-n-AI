import { useCallback, useEffect, useState } from 'react'
import { apiRequest, downloadAccountingExcel, getErrorMessage, type Invoice } from '../api'
import { EmptyState, MetricCard, PageHeading, type Notice } from './shared'
import { formatCurrency } from './utils'

export function AccountingPage({ setNotice }: { setNotice: (notice: Notice) => void }) {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [filter, setFilter] = useState('all')
  const [error, setError] = useState('')
  const [savingId, setSavingId] = useState<number | null>(null)
  const refresh = useCallback(() => {
    apiRequest<{ invoices: Invoice[] }>('/api/accounting')
      .then(({ invoices: rows }) => { setInvoices(rows); setError('') })
      .catch((reason: unknown) => setError(getErrorMessage(reason)))
  }, [])
  useEffect(() => { refresh() }, [refresh])
  const filtered = invoices.filter((invoice) => filter === 'all' || invoice.payment_status === filter)
  const paid = invoices.filter((invoice) => invoice.payment_status === 'paid')
  const unpaid = invoices.filter((invoice) => invoice.payment_status !== 'paid')
  const filteredTotal = filtered.reduce((sum, invoice) => sum + (invoice.tong_thanh_toan || 0), 0)

  async function setPayment(invoiceId: number, status: string) {
    setSavingId(invoiceId)
    try {
      await apiRequest(`/api/invoices/${invoiceId}/payment-status`, { method: 'PUT', body: { status } })
      setNotice({ kind: 'success', text: 'Đã cập nhật trạng thái thanh toán.' })
      refresh()
    } catch (reason) { setError(getErrorMessage(reason)) }
    finally { setSavingId(null) }
  }

  return (
    <div className="workspace-content">
      <PageHeading
        eyebrow="🧮 QUẢN LÝ TÀI CHÍNH & BÁO CÁO"
        title="Hạch toán kế toán"
        description="Tổng hợp số liệu hóa đơn đã xác nhận, theo dõi dòng tiền thanh toán và xuất dữ liệu báo cáo kế toán."
        action={<button className="button primary" onClick={() => downloadAccountingExcel(filter).catch((reason: unknown) => setError(getErrorMessage(reason)))}>↓ Xuất báo cáo Excel</button>}
      />
      {error && <div className="inline-error" role="alert">{error}</div>}
      <div className="metric-grid">
        <MetricCard label="Đã xác nhận" value={invoices.length} detail="Hóa đơn sẵn sàng hạch toán" tone="blue" icon="📊" />
        <MetricCard label="Đã thanh toán" value={paid.length} detail={formatCurrency(paid.reduce((sum, row) => sum + (row.tong_thanh_toan || 0), 0))} tone="green" icon="✅" />
        <MetricCard label="Chưa thanh toán" value={unpaid.length} detail={formatCurrency(unpaid.reduce((sum, row) => sum + (row.tong_thanh_toan || 0), 0))} tone="amber" icon="⏳" />
        <MetricCard label="Theo bộ lọc" value={formatCurrency(filteredTotal)} detail={`${filtered.length} hóa đơn`} tone="violet" icon="💰" />
      </div>
      <section className="workspace-panel">
        <div className="panel-heading"><div><h2>Danh sách hạch toán chi tiết</h2><p>Thay đổi trạng thái thanh toán sẽ được lưu tức thì vào hệ thống.</p></div><select aria-label="Lọc tình trạng thanh toán" onChange={(event) => setFilter(event.target.value)} value={filter}><option value="all">Tất cả tình trạng</option><option value="unpaid">Chưa thanh toán</option><option value="paid">Đã thanh toán</option></select></div>
        {filtered.length ? (
          <div className="table-scroll"><table className="data-table"><thead><tr><th>Ngày lập</th><th>Nhà cung cấp</th><th>Mã số thuế</th><th>Số hóa đơn</th><th>Tiền hàng</th><th>VAT</th><th>Tổng thanh toán</th><th>Tình trạng</th></tr></thead>
            <tbody>{filtered.map((invoice) => <tr key={invoice.id}><td className="date-cell">{invoice.ngay_lap || '—'}</td><td style={{ fontWeight: 600 }}>{invoice.ten_cong_ty_ban || '—'}</td><td style={{ fontFamily: 'var(--font-mono)', color: '#4F46E5', fontSize: '12px' }}>{invoice.ma_so_thue_ban || '—'}</td><td><span className="inv-code">{invoice.so_hoa_don || '—'}</span></td><td className="money-cell">{formatCurrency(invoice.tong_tien_hang)}</td><td className="money-cell">{formatCurrency(invoice.tien_thue_vat)}</td><td className="money-cell" style={{ color: '#2563EB' }}>{formatCurrency(invoice.tong_thanh_toan)}</td><td><select aria-label={`Thanh toán hóa đơn ${invoice.id}`} disabled={savingId === invoice.id} onChange={(event) => setPayment(invoice.id, event.target.value)} value={invoice.payment_status || 'unpaid'} style={{ color: invoice.payment_status === 'paid' ? '#15803D' : '#92400E', fontWeight: 600 }}><option value="unpaid">Chưa thanh toán</option><option value="paid">Đã thanh toán</option></select></td></tr>)}</tbody>
          </table></div>
        ) : <EmptyState title="Chưa có dữ liệu hạch toán" description="Hóa đơn đã xác nhận sẽ xuất hiện tại đây." />}
      </section>
    </div>
  )
}
