import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiRequest, getErrorMessage, type Invoice, type Job, type User } from '../api'
import { EmptyState, MetricCard, PageHeading, StatusBadge } from './shared'
import { ACCOUNTING_TITLES, formatCurrency, formatDate, invoiceItems, parseDate } from './utils'

export function ReportsPage({ user }: { user: User }) {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [confirmed, setConfirmed] = useState<Invoice[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [tab, setTab] = useState<'overview' | 'audit' | 'duplicates' | 'activity'>('overview')
  const [error, setError] = useState('')

  const refresh = useCallback(() => {
    apiRequest<{ invoices: Invoice[]; recent_jobs: Job[] }>('/api/reports')
      .then((result) => {
        setInvoices(result.invoices)
        setConfirmed(result.invoices.filter((invoice) => invoice.accounting_status === 'confirmed'))
        setJobs(result.recent_jobs)
        setError('')
      })
      .catch((reason: unknown) => setError(getErrorMessage(reason)))
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const findings = useMemo(() => invoices.flatMap((invoice) => {
    const issues: string[] = []
    if (!invoice.ma_so_thue_ban) issues.push('Thiếu mã số thuế bên bán')
    if (!invoice.ten_cong_ty_ban) issues.push('Thiếu tên công ty bên bán')
    if (!invoice.ngay_lap) issues.push('Thiếu ngày lập hóa đơn')
    if (!invoice.thue_suat_vat) issues.push('Thiếu thuế suất VAT')
    const amounts = [invoice.tong_tien_hang, invoice.tien_thue_vat, invoice.tong_thanh_toan]
    if (amounts.some((amount) => amount == null || amount < 0)) issues.push('Tổng tiền hoặc tiền VAT không hợp lệ')
    if (amounts.every((amount): amount is number => amount != null) && Math.abs(amounts[0] + amounts[1] - amounts[2]) > 1) {
      issues.push('Tiền hàng + VAT không khớp tổng thanh toán')
    }
    const items = invoiceItems(invoice)
    if (items.some((item) => item.so_luong != null && item.don_gia != null && item.thanh_tien != null
      && Math.abs(Number(item.so_luong) * Number(item.don_gia) - Number(item.thanh_tien)) > 1)) {
      issues.push('Số lượng × đơn giá không khớp thành tiền')
    }
    return issues.length ? [{ invoice, issues }] : []
  }), [invoices])

  const duplicateGroups = useMemo(() => {
    const groups = new Map<string, Invoice[]>()
    for (const invoice of invoices) {
      const taxId = (invoice.ma_so_thue_ban || '').replace(/\W/g, '').toUpperCase()
      const number = (invoice.so_hoa_don || '').replace(/\W/g, '').toUpperCase()
      if (!taxId || !number) continue
      const key = `${taxId}:${number}`
      groups.set(key, [...(groups.get(key) ?? []), invoice])
    }
    return [...groups.entries()].filter(([, group]) => group.length > 1)
  }, [invoices])

  const monthly = useMemo(() => {
    const values = new Map<string, number>()
    for (const invoice of confirmed) {
      const rawDate = invoice.ngay_lap ? parseDate(invoice.ngay_lap) : new Date(invoice.created_at || '')
      const date = Number.isNaN(rawDate.getTime()) ? new Date(invoice.created_at || '') : rawDate
      if (Number.isNaN(date.getTime())) continue
      const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
      values.set(key, (values.get(key) ?? 0) + (invoice.tong_thanh_toan || 0))
    }
    return [...values.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(-6)
  }, [confirmed])
  const maximum = Math.max(...monthly.map(([, value]) => value), 1)
  const suppliers = useMemo(() => {
    const totals = new Map<string, { count: number; amount: number }>()
    for (const invoice of confirmed) {
      const name = invoice.ten_cong_ty_ban || 'Chưa xác định'
      const current = totals.get(name) ?? { count: 0, amount: 0 }
      totals.set(name, { count: current.count + 1, amount: current.amount + (invoice.tong_thanh_toan || 0) })
    }
    return [...totals.entries()].sort(([, a], [, b]) => b.amount - a.amount).slice(0, 5)
  }, [confirmed])
  const totalAmount = confirmed.reduce((sum, invoice) => sum + (invoice.tong_thanh_toan || 0), 0)
  const goodsAmount = confirmed.reduce((sum, invoice) => sum + (invoice.tong_tien_hang || 0), 0)
  const [today] = useState(() => new Date().toDateString())
  const todayJobs = jobs.filter((job) => job.created_at && new Date(job.created_at).toDateString() === today)

  const tabs: { id: typeof tab; title: string }[] = [
    { id: 'overview', title: '📊 Tổng quan tài chính' },
    { id: 'audit', title: `⚠️ Kiểm toán (${findings.length})` },
    { id: 'duplicates', title: `🔁 Đối soát trùng (${duplicateGroups.length})` },
    { id: 'activity', title: '⏱️ Nhật ký hoạt động' },
  ]

  return (
    <div className="workspace-content">
      <PageHeading
        eyebrow="📈 BI & FINANCIAL INTELLIGENCE"
        title="Báo cáo tổng hợp & Kiểm toán"
        description={user.role === 'admin' ? 'Phân tích chỉ số tài chính toàn hệ thống, rà soát tính toàn vẹn dữ liệu và đối soát lịch sử hoạt động.' : 'Phân tích các hóa đơn và lịch sử hoạt động thuộc tài khoản của bạn.'}
        action={<button className="button subtle" onClick={refresh}>↻ Cập nhật</button>}
      />
      {error && <div className="inline-error" role="alert">{error}</div>}
      <div className="report-tabs">{tabs.map((item) => <button className={tab === item.id ? 'active' : ''} key={item.id} onClick={() => setTab(item.id)}>{item.title}</button>)}</div>
      {tab === 'overview' && (
        <>
          <div className="metric-grid">
            <MetricCard label="Hóa đơn đã hạch toán" value={confirmed.length} detail="Đã xác nhận" tone="blue" icon="📄" />
            <MetricCard label="Tổng giá trị" value={formatCurrency(totalAmount)} detail="Theo hóa đơn đã duyệt" tone="green" icon="✅" />
            <MetricCard label="Thuế GTGT" value={formatCurrency(totalAmount - goodsAmount)} detail="Tổng thanh toán − tiền hàng" tone="amber" icon="📊" />
            <MetricCard label="Giá trị trung bình" value={formatCurrency(confirmed.length ? totalAmount / confirmed.length : 0)} detail="Trên mỗi hóa đơn" tone="violet" icon="💰" />
          </div>
          <div className="report-grid">
            <section className="workspace-panel chart-panel">
              <div className="panel-heading"><div><h2>Doanh số / Giá trị theo tháng</h2><p>Sáu tháng gần nhất · theo ngày lập hóa đơn</p></div></div>
              {monthly.length ? <div className="bar-chart">{monthly.map(([month, value], index) => <div className="bar-column" key={month}><span>{formatCurrency(value)}</span><div className="bar-track"><i className={index === monthly.length - 1 ? 'current' : ''} style={{ height: `${Math.max(4, value / maximum * 100)}%` }} /></div><small>{`T${Number(month.slice(5))}/${month.slice(0, 4)}`}</small></div>)}</div> : <EmptyState title="Chưa có dữ liệu hạch toán" description="Xác nhận hóa đơn để xem báo cáo theo tháng." />}
            </section>
            <section className="workspace-panel">
              <div className="panel-heading"><div><h2>Cơ cấu giá trị thanh toán</h2><p>Tỷ lệ tiền hàng và thuế GTGT</p></div></div>
              <div className="composition-total">{formatCurrency(totalAmount)}</div>
              <div className="composition-bar"><i style={{ width: `${totalAmount ? goodsAmount / totalAmount * 100 : 0}%` }} /></div>
              <div className="composition-legend"><span><i className="goods-dot" />Tiền hàng</span><strong>{formatCurrency(goodsAmount)}</strong></div>
              <div className="composition-legend"><span><i className="vat-dot" />Thuế GTGT</span><strong>{formatCurrency(totalAmount - goodsAmount)}</strong></div>
            </section>
          </div>
          <section className="workspace-panel supplier-panel">
            <div className="panel-heading"><div><h2>Top 5 Nhà cung cấp lớn nhất</h2><p>Theo tổng giá trị thanh toán trên các hóa đơn đã được xác nhận.</p></div></div>
            {suppliers.length ? suppliers.map(([name, data], index) => <div className="supplier-row" key={name}><span className="supplier-rank">{String(index + 1).padStart(2, '0')}</span><div className="supplier-name"><strong>{name}</strong><div><i style={{ width: `${data.amount / Math.max(suppliers[0][1].amount, 1) * 100}%` }} /></div></div><span className="supplier-value">{formatCurrency(data.amount)}<small>{data.count} hóa đơn</small></span></div>) : <EmptyState title="Chưa có nhà cung cấp" description="Báo cáo sẽ xuất hiện khi có hóa đơn đã xác nhận." />}
          </section>
        </>
      )}
      {tab === 'audit' && (
        <section className="workspace-panel">
          <div className="panel-heading"><div><h2>Kiểm tra logic &amp; số học hóa đơn</h2><p>Những cảnh báo hỗ trợ đối chiếu, không tự động sửa dữ liệu gốc.</p></div><span className="count-pill">{findings.length} hóa đơn cần xem</span></div>
          {findings.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>ID</th><th>Nhà cung cấp</th><th>Ngày lập</th><th>Trạng thái</th><th>Chi tiết cần rà soát</th></tr></thead><tbody>{findings.map(({ invoice, issues }) => <tr key={invoice.id}><td><span className="inv-code">#{invoice.id}</span></td><td><strong>{invoice.ten_cong_ty_ban || 'Chưa xác định'}</strong></td><td className="date-cell">{invoice.ngay_lap || 'Chưa có'}</td><td><span className={`accounting-pill ${invoice.accounting_status}`}>{ACCOUNTING_TITLES[invoice.accounting_status]}</span></td><td style={{ color: '#B91C1C' }}>{issues.join(' · ')}</td></tr>)}</tbody></table></div> : <EmptyState title="Không phát hiện sai lệch" description="Các hóa đơn hiện có đều vượt qua những kiểm tra số học cơ bản." />}
        </section>
      )}
      {tab === 'duplicates' && (
        <section className="workspace-panel">
          <div className="panel-heading"><div><h2>Đối soát hóa đơn có khả năng trùng</h2><p>Nhóm theo mã số thuế bên bán và số hóa đơn; đối chiếu ngày, tổng tiền.</p></div><span className="count-pill">{duplicateGroups.length} nhóm trùng</span></div>
          {duplicateGroups.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>MST bên bán</th><th>Số hóa đơn</th><th>Bản ghi liên quan</th><th>Ngày lập</th><th>Tổng tiền</th><th>Đánh giá</th></tr></thead><tbody>{duplicateGroups.map(([key, group]) => { const reference = group[0]; const datesMatch = group.every((invoice) => invoice.ngay_lap === reference.ngay_lap); const amountsMatch = group.every((invoice) => invoice.tong_thanh_toan != null && reference.tong_thanh_toan != null && Math.abs(invoice.tong_thanh_toan - reference.tong_thanh_toan) <= 1); return <tr key={key}><td style={{ fontFamily: 'var(--font-mono)', color: '#4F46E5', fontWeight: 600 }}>{reference.ma_so_thue_ban}</td><td><span className="inv-code">{reference.so_hoa_don}</span></td><td>{group.map((invoice) => <span key={invoice.id} className="file-chip" style={{ marginRight: '4px' }}>#{invoice.id}</span>)}</td><td>{datesMatch ? 'Khớp' : 'Khác nhau'}</td><td className="money-cell">{amountsMatch ? 'Khớp' : 'Khác nhau'}</td><td><span className={`accounting-pill ${datesMatch && amountsMatch ? 'confirmed' : 'pending'}`}>{datesMatch && amountsMatch ? 'Trùng hoàn toàn' : 'Nghi vấn trùng'}</span></td></tr> })}</tbody></table></div> : <EmptyState title="Không phát hiện hóa đơn trùng" description="Không có nhóm trùng số hóa đơn và mã số thuế bên bán." />}
        </section>
      )}
      {tab === 'activity' && (
        <section className="workspace-panel">
          <div className="panel-heading"><div><h2>Tiến trình xử lý hôm nay</h2><p>Trạng thái các công việc OCR và bóc tách gần đây.</p></div></div>
          {todayJobs.length ? <div className="job-list">{todayJobs.map((job) => <div className="job-row" key={job.id}><span className="document-icon">▤</span><div className="job-info"><strong>{job.file_name || `Hóa đơn #${job.id}`}</strong><small>{formatDate(job.created_at)}</small></div><StatusBadge status={job.status} /></div>)}</div> : <EmptyState title="Chưa ghi nhận hoạt động hôm nay" description="Tệp được tải lên sẽ xuất hiện trong nhật ký này." />}
        </section>
      )}
    </div>
  )
}
