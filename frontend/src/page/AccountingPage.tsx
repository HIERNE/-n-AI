import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiRequest, downloadAccountingExcel, getErrorMessage, type Invoice } from '../api'
import { EmptyState, MetricCard, PageHeading, type Notice } from './shared'
import { formatCurrency, getInvoiceMonthYear } from './utils'

export function AccountingPage({ setNotice }: { setNotice: (notice: Notice) => void }) {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [paymentFilter, setPaymentFilter] = useState<'all' | 'paid' | 'unpaid'>('all')
  const [selectedYear, setSelectedYear] = useState<number | 'all'>('all')
  const [selectedMonth, setSelectedMonth] = useState<number | 'all'>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [error, setError] = useState('')
  const [savingId, setSavingId] = useState<number | null>(null)
  const [exporting, setExporting] = useState(false)

  const refresh = useCallback(() => {
    apiRequest<{ invoices: Invoice[] }>('/api/accounting')
      .then(({ invoices: rows }) => {
        setInvoices(rows)
        setError('')
      })
      .catch((reason: unknown) => setError(getErrorMessage(reason)))
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Extract distinct available years from invoices
  const availableYears = useMemo(() => {
    const yearsSet = new Set<number>()
    const currentYear = new Date().getFullYear()
    yearsSet.add(currentYear)
    for (const inv of invoices) {
      const my = getInvoiceMonthYear(inv)
      if (my) yearsSet.add(my.year)
    }
    return Array.from(yearsSet).sort((a, b) => b - a)
  }, [invoices])

  // Count invoices in each month for the selected year
  const monthCounts = useMemo(() => {
    const counts: Record<number, number> = {}
    for (let m = 1; m <= 12; m++) counts[m] = 0
    for (const inv of invoices) {
      const my = getInvoiceMonthYear(inv)
      if (my && (selectedYear === 'all' || my.year === selectedYear)) {
        counts[my.month] = (counts[my.month] || 0) + 1
      }
    }
    return counts
  }, [invoices, selectedYear])

  // Filter invoices by Payment Status, Month, Year, and Search Query
  const filtered = useMemo(() => {
    return invoices.filter((invoice) => {
      if (paymentFilter !== 'all' && invoice.payment_status !== paymentFilter) {
        return false
      }
      const my = getInvoiceMonthYear(invoice)
      if (selectedYear !== 'all') {
        if (!my || my.year !== selectedYear) return false
      }
      if (selectedMonth !== 'all') {
        if (!my || my.month !== selectedMonth) return false
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim()
        const matchSupplier = (invoice.ten_cong_ty_ban || '').toLowerCase().includes(q)
        const matchTax = (invoice.ma_so_thue_ban || '').toLowerCase().includes(q)
        const matchNumber = (invoice.so_hoa_don || '').toLowerCase().includes(q)
        const matchId = String(invoice.id).includes(q)
        if (!matchSupplier && !matchTax && !matchNumber && !matchId) return false
      }
      return true
    })
  }, [invoices, paymentFilter, selectedYear, selectedMonth, searchQuery])

  // Financial metrics for current period
  const paidRows = useMemo(() => filtered.filter((r) => r.payment_status === 'paid'), [filtered])
  const unpaidRows = useMemo(() => filtered.filter((r) => r.payment_status !== 'paid'), [filtered])
  const totalGoods = useMemo(() => filtered.reduce((sum, r) => sum + (r.tong_tien_hang || 0), 0), [filtered])
  const totalVat = useMemo(() => filtered.reduce((sum, r) => sum + (r.tien_thue_vat || 0), 0), [filtered])
  const filteredTotal = useMemo(() => filtered.reduce((sum, r) => sum + (r.tong_thanh_toan || 0), 0), [filtered])
  const paidTotal = useMemo(() => paidRows.reduce((sum, r) => sum + (r.tong_thanh_toan || 0), 0), [paidRows])
  const unpaidTotal = useMemo(() => unpaidRows.reduce((sum, r) => sum + (r.tong_thanh_toan || 0), 0), [unpaidRows])

  // Title of current period
  const periodTitle = useMemo(() => {
    if (selectedMonth !== 'all' && selectedYear !== 'all') {
      return `Tháng ${String(selectedMonth).padStart(2, '0')}/${selectedYear}`
    }
    if (selectedMonth !== 'all') {
      return `Tháng ${String(selectedMonth).padStart(2, '0')}`
    }
    if (selectedYear !== 'all') {
      return `Năm ${selectedYear}`
    }
    return 'Toàn bộ kỳ kế toán'
  }, [selectedMonth, selectedYear])

  const periodBadgeText = useMemo(() => {
    if (selectedMonth !== 'all' && selectedYear !== 'all') {
      return `T${String(selectedMonth).padStart(2, '0')}/${selectedYear}`
    }
    if (selectedMonth !== 'all') {
      return `T${String(selectedMonth).padStart(2, '0')}`
    }
    if (selectedYear !== 'all') {
      return `${selectedYear}`
    }
    return 'Tất cả'
  }, [selectedMonth, selectedYear])

  async function setPayment(invoiceId: number, status: string) {
    setSavingId(invoiceId)
    try {
      await apiRequest(`/api/invoices/${invoiceId}/payment-status`, { method: 'PUT', body: { status } })
      setNotice({ kind: 'success', text: 'Đã cập nhật trạng thái thanh toán.' })
      refresh()
    } catch (reason) {
      setError(getErrorMessage(reason))
    } finally {
      setSavingId(null)
    }
  }

  async function handleExportExcel() {
    setExporting(true)
    setError('')
    try {
      await downloadAccountingExcel({
        paymentStatus: paymentFilter,
        month: selectedMonth,
        year: selectedYear,
      })
      setNotice({ kind: 'success', text: `Đã xuất sổ hạch toán Excel cho ${periodTitle}.` })
    } catch (reason) {
      setError(getErrorMessage(reason))
    } finally {
      setExporting(false)
    }
  }

  function resetFilters() {
    setSelectedYear('all')
    setSelectedMonth('all')
    setPaymentFilter('all')
    setSearchQuery('')
  }

  const isFilterActive = selectedYear !== 'all' || selectedMonth !== 'all' || paymentFilter !== 'all' || searchQuery.trim() !== ''

  return (
    <div className="workspace-content">
      <PageHeading
        eyebrow="🧮 QUẢN LÝ TÀI CHÍNH & HẠCH TOÁN DOANH NGHIỆP"
        title="Hạch toán kế toán"
        description="Tổng hợp số liệu hóa đơn đã xác nhận, theo dõi công nợ dòng tiền và xuất sổ hạch toán định kỳ theo tháng/năm."
        action={
          <button
            className="btn-export-excel"
            disabled={exporting}
            onClick={handleExportExcel}
            title={`Xuất file Excel cho ${periodTitle}`}
          >
            {exporting ? '⏳ Đang kết xuất...' : `📥 Xuất Excel (${periodBadgeText})`}
          </button>
        }
      />

      {error && <div className="inline-error" role="alert">{error}</div>}

      {/* BỘ LỌC KỲ KẾ TOÁN & CÔNG CỤ KỸ THUẬT */}
      <section className="accounting-period-card">
        <div className="period-card-header">
          <div className="period-card-title">
            <span>📅</span> BỘ LỌC KỲ KẾ TOÁN &amp; CÔNG NỢ
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="period-badge-pill">
              Kỳ: <strong>{periodTitle}</strong> · <strong>{filtered.length}</strong> HĐ
            </span>
            {isFilterActive && (
              <button
                type="button"
                className="button subtle small"
                onClick={resetFilters}
                title="Khôi phục toàn bộ bộ lọc về mặc định"
                style={{ padding: '4px 8px', fontSize: '11.5px' }}
              >
                ↺ Đặt lại
              </button>
            )}
          </div>
        </div>

        {/* Hàng lọc 1: Năm, Thanh toán, Tìm kiếm */}
        <div className="period-filter-row">
          <div className="filter-group">
            <label className="filter-label" htmlFor="acc-year-select">Năm tài chính:</label>
            <select
              id="acc-year-select"
              value={selectedYear}
              onChange={(e) => setSelectedYear(e.target.value === 'all' ? 'all' : Number(e.target.value))}
              style={{ minWidth: '140px' }}
            >
              <option value="all">Tất cả các năm</option>
              {availableYears.map((year) => (
                <option key={year} value={year}>
                  Năm {year}
                </option>
              ))}
            </select>
          </div>

          <div className="filter-group">
            <label className="filter-label" htmlFor="acc-status-select">Thanh toán:</label>
            <select
              id="acc-status-select"
              value={paymentFilter}
              onChange={(e) => setPaymentFilter(e.target.value as 'all' | 'paid' | 'unpaid')}
              style={{ minWidth: '170px' }}
            >
              <option value="all">Tất cả tình trạng</option>
              <option value="paid">✅ Đã thanh toán</option>
              <option value="unpaid">⏳ Chưa thanh toán (Nợ)</option>
            </select>
          </div>

          <div className="filter-group" style={{ flex: 1, minWidth: '240px' }}>
            <label className="filter-label" htmlFor="acc-search-input">Tìm kiếm:</label>
            <input
              id="acc-search-input"
              type="text"
              placeholder="Tìm nhà cung cấp, mã số thuế, số HĐ..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: '8px',
                border: '1px solid #E2E8F0',
                fontSize: '13px',
              }}
            />
          </div>
        </div>

        {/* Hàng lọc 2: Thanh 12 Tháng Kế Toán (Segmented Bar) */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span className="filter-label">Chọn tháng hạch toán:</span>
            {selectedMonth !== 'all' && (
              <span style={{ fontSize: '11.5px', color: '#4F46E5', fontWeight: 600 }}>
                Đang xem Tháng {selectedMonth}
              </span>
            )}
          </div>
          <div className="month-segmented-bar">
            <button
              type="button"
              className={`month-btn ${selectedMonth === 'all' ? 'active' : ''}`}
              onClick={() => setSelectedMonth('all')}
              title="Xem tất cả các tháng trong năm"
            >
              Tất cả
            </button>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((m) => {
              const count = monthCounts[m] || 0
              const isSelected = selectedMonth === m
              return (
                <button
                  key={m}
                  type="button"
                  className={`month-btn ${isSelected ? 'active' : ''} ${count > 0 ? 'has-invoices' : ''}`}
                  onClick={() => setSelectedMonth(m)}
                  title={`Tháng ${m} (${count} hóa đơn)`}
                >
                  T{String(m).padStart(2, '0')}
                  {count > 0 && <span className="month-count-dot">{count}</span>}
                </button>
              )
            })}
          </div>
        </div>
      </section>

      {/* 4 THẺ CHỈ SỐ TÀI CHÍNH THEO KỲ ĐÃ CHỌN */}
      <div className="metric-grid">
        <MetricCard
          label="Hóa đơn trong kỳ"
          value={filtered.length}
          detail={`Kỳ: ${periodTitle}`}
          tone="blue"
          icon="📊"
        />
        <MetricCard
          label="Đã thanh toán"
          value={paidRows.length}
          detail={formatCurrency(paidTotal)}
          tone="green"
          icon="✅"
        />
        <MetricCard
          label="Chưa thanh toán (Công nợ)"
          value={unpaidRows.length}
          detail={formatCurrency(unpaidTotal)}
          tone="amber"
          icon="⏳"
        />
        <MetricCard
          label="Tổng giá trị hạch toán"
          value={formatCurrency(filteredTotal)}
          detail={`Thuế VAT: ${formatCurrency(totalVat)}`}
          tone="violet"
          icon="💰"
        />
      </div>

      {/* DANH SÁCH CHỨNG TỪ HẠCH TOÁN CHI TIẾT */}
      <section className="workspace-panel">
        <div className="panel-heading">
          <div>
            <h2>Danh sách chứng từ hạch toán</h2>
            <p>
              Hiển thị hóa đơn đã duyệt hạch toán cho {periodTitle}. Cập nhật trạng thái thanh toán trực tiếp.
            </p>
          </div>
          <span style={{ fontSize: '12px', fontWeight: 600, color: '#64748B' }}>
            Hiển thị: <strong style={{ color: '#0F172A' }}>{filtered.length}</strong> / {invoices.length} chứng từ
          </span>
        </div>

        {filtered.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: '36px', textAlign: 'center' }}>#</th>
                  <th style={{ width: '85px' }}>Mã HĐ</th>
                  <th>Ngày lập</th>
                  <th>Nhà cung cấp (Bên bán)</th>
                  <th>Mã số thuế</th>
                  <th>Số hóa đơn</th>
                  <th style={{ textAlign: 'right' }}>Tiền hàng</th>
                  <th style={{ textAlign: 'right' }}>VAT</th>
                  <th style={{ textAlign: 'right' }}>Tổng thanh toán</th>
                  <th style={{ width: '150px', textAlign: 'center' }}>Tình trạng</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((invoice, idx) => (
                  <tr key={invoice.id}>
                    <td style={{ textAlign: 'center', fontWeight: 600, color: '#64748B' }}>
                      {idx + 1}
                    </td>
                    <td>
                      <span className="inv-code">#{String(invoice.id).padStart(4, '0')}</span>
                    </td>
                    <td className="date-cell">{invoice.ngay_lap || '—'}</td>
                    <td style={{ fontWeight: 600 }}>{invoice.ten_cong_ty_ban || '—'}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', color: '#4F46E5', fontSize: '12px' }}>
                      {invoice.ma_so_thue_ban || '—'}
                    </td>
                    <td>
                      <span className="inv-code">{invoice.so_hoa_don || '—'}</span>
                    </td>
                    <td className="money-cell">{formatCurrency(invoice.tong_tien_hang)}</td>
                    <td className="money-cell">{formatCurrency(invoice.tien_thue_vat)}</td>
                    <td className="money-cell" style={{ color: '#2563EB', fontWeight: 700 }}>
                      {formatCurrency(invoice.tong_thanh_toan)}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <select
                        aria-label={`Thanh toán hóa đơn ${invoice.id}`}
                        disabled={savingId === invoice.id}
                        onChange={(event) => setPayment(invoice.id, event.target.value)}
                        value={invoice.payment_status || 'unpaid'}
                        className={`payment-select ${invoice.payment_status === 'paid' ? 'paid' : 'unpaid'}`}
                      >
                        <option value="unpaid">⏳ Chưa thanh toán</option>
                        <option value="paid">✅ Đã thanh toán</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={6} style={{ fontWeight: 700, color: '#1E293B', padding: '12px 14px' }}>
                    TỔNG CỘNG ({filtered.length} HÓA ĐƠN TRONG {periodTitle.toUpperCase()})
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: 700, color: '#0F172A', padding: '12px 14px' }}>
                    {formatCurrency(totalGoods)}
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: 700, color: '#0F172A', padding: '12px 14px' }}>
                    {formatCurrency(totalVat)}
                  </td>
                  <td style={{ textAlign: 'right', fontWeight: 700, color: '#2563EB', fontSize: '14px', padding: '12px 14px' }}>
                    {formatCurrency(filteredTotal)}
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>
        ) : (
          <EmptyState
            title={`Không có dữ liệu trong ${periodTitle}`}
            description="Không tìm thấy hóa đơn nào phù hợp với kỳ kế toán hoặc bộ lọc hiện tại."
            action={
              isFilterActive ? (
                <button type="button" className="button subtle small" onClick={resetFilters}>
                  ↺ Xem tất cả kỳ kế toán
                </button>
              ) : undefined
            }
          />
        )}
      </section>
    </div>
  )
}
