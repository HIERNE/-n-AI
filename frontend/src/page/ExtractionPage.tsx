import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { apiRequest, getErrorMessage, type Invoice, type User } from '../api'
import { EmptyState, PageHeading, type Notice } from './shared'
import { ACCOUNTING_TITLES, formatCurrency, invoiceItems } from './utils'

export function ExtractionPage({ user, setNotice }: {
  user: User
  setNotice: (notice: Notice) => void
}) {
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const isAdmin = user.role === 'admin'
  const selected = invoices.find((invoice) => invoice.id === selectedId) ?? null

  // Items table states
  type EditableItem = {
    id: string
    ten_hang: string
    don_vi_tinh: string
    so_luong: string
    don_gia: string
    thanh_tien: string
  }
  const [items, setItems] = useState<EditableItem[]>([])

  // Document preview states
  type AvailableFile = {
    path: string
    name: string
    folder: string
    size: number
    is_pdf: boolean
  }
  const [showRelink, setShowRelink] = useState(false)
  const [availableFiles, setAvailableFiles] = useState<AvailableFile[]>([])
  const [relinkPath, setRelinkPath] = useState('')
  const [relinking, setRelinking] = useState(false)

  const canEdit = isAdmin || selected?.accounting_status === 'pending'
  const isPdf = Boolean(selected?.source_image?.toLowerCase().endsWith('.pdf'))

  const refresh = useCallback(async () => {
    try {
      const result = await apiRequest<{ invoices: Invoice[] }>('/api/invoices')
      setInvoices(result.invoices)
      setSelectedId((id) => (id && result.invoices.some((inv) => inv.id === id) ? id : result.invoices[0]?.id ?? null))
      setError('')
    } catch (reason) {
      setError(getErrorMessage(reason))
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const loadAvailableFiles = useCallback(async () => {
    try {
      const res = await apiRequest<{ files: AvailableFile[] }>('/api/files/available')
      setAvailableFiles(res.files || [])
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    if (!selected) return
    setFields({
      ma_so_thue_ban: selected.ma_so_thue_ban || '',
      ten_cong_ty_ban: selected.ten_cong_ty_ban || '',
      so_hoa_don: selected.so_hoa_don || '',
      ma_so_thue_mua: selected.ma_so_thue_mua || '',
      ten_cong_ty_mua: selected.ten_cong_ty_mua || '',
      ngay_lap: selected.ngay_lap || '',
      thue_suat_vat: selected.thue_suat_vat || '',
      tong_tien_hang: selected.tong_tien_hang == null ? '' : String(selected.tong_tien_hang),
      tien_thue_vat: selected.tien_thue_vat == null ? '' : String(selected.tien_thue_vat),
      tong_thanh_toan: selected.tong_thanh_toan == null ? '' : String(selected.tong_thanh_toan),
    })

    const rawList = invoiceItems(selected)
    const parsedItems: EditableItem[] = rawList.map((it, idx) => ({
      id: `item-${selected.id}-${idx}-${Math.random().toString(36).slice(2, 6)}`,
      ten_hang: String(it.ten_hang ?? (it as Record<string, unknown>).ten_san_pham ?? (it as Record<string, unknown>).mo_ta ?? ''),
      don_vi_tinh: String((it as Record<string, unknown>).don_vi_tinh ?? (it as Record<string, unknown>).dvt ?? ''),
      so_luong: it.so_luong == null ? '' : String(it.so_luong),
      don_gia: it.don_gia == null ? '' : String(it.don_gia),
      thanh_tien: it.thanh_tien == null ? '' : String(it.thanh_tien),
    }))
    setItems(parsedItems)
    setShowRelink(false)
    setRelinkPath('')
  }, [selected])

  function cleanForJson(list: EditableItem[]) {
    return list.map((it) => {
      const row: Record<string, unknown> = { ten_hang: it.ten_hang }
      if (it.don_vi_tinh) row.don_vi_tinh = it.don_vi_tinh
      if (it.so_luong !== '') row.so_luong = Number(it.so_luong)
      if (it.don_gia !== '') row.don_gia = Number(it.don_gia)
      if (it.thanh_tien !== '') row.thanh_tien = Number(it.thanh_tien)
      return row
    })
  }

  function addItemRow() {
    const newItem: EditableItem = {
      id: `item-new-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      ten_hang: '',
      don_vi_tinh: '',
      so_luong: '1',
      don_gia: '0',
      thanh_tien: '0',
    }
    setItems((prev) => [...prev, newItem])
  }

  function removeItemRow(index: number) {
    setItems((prev) => prev.filter((_, i) => i !== index))
  }

  function updateItem(index: number, key: keyof EditableItem, value: string) {
    setItems((prev) => {
      const next = [...prev]
      const current = { ...next[index], [key]: value }
      if (key === 'so_luong' || key === 'don_gia') {
        const q = key === 'so_luong' ? Number(value) : Number(current.so_luong)
        const p = key === 'don_gia' ? Number(value) : Number(current.don_gia)
        if (Number.isFinite(q) && Number.isFinite(p) && q >= 0 && p >= 0) {
          current.thanh_tien = String(Math.round(q * p))
        }
      }
      next[index] = current
      return next
    })
  }

  const totalCalculatedGoods = useMemo(() => {
    return items.reduce((sum, it) => sum + (Number(it.thanh_tien) || 0), 0)
  }, [items])

  const totalQuantity = useMemo(() => {
    return items.reduce((sum, it) => sum + (Number(it.so_luong) || 0), 0)
  }, [items])

  function syncTotalToGoods() {
    setFields((prev) => {
      const vat = Number(prev.tien_thue_vat) || 0
      return {
        ...prev,
        tong_tien_hang: String(totalCalculatedGoods),
        tong_thanh_toan: String(totalCalculatedGoods + vat),
      }
    })
    setNotice({
      kind: 'success',
      text: 'Đã đồng bộ tổng tiền hàng từ danh mục vào thông tin tài chính.',
    })
  }

  async function handleRelinkSource() {
    if (!selected || !relinkPath) return
    setRelinking(true)
    try {
      await apiRequest(`/api/invoices/${selected.id}/source-image`, {
        method: 'PUT',
        body: { source_image: relinkPath },
      })
      setNotice({ kind: 'success', text: `Đã liên kết tệp ảnh mới cho hóa đơn #${selected.id}.` })
      setShowRelink(false)
      await refresh()
    } catch (reason) {
      setNotice({ kind: 'error', text: getErrorMessage(reason) })
    } finally {
      setRelinking(false)
    }
  }

  async function saveInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected) return
    setSaving(true)
    try {
      const finalItems = cleanForJson(items)
      const numberKeys = ['tong_tien_hang', 'tien_thue_vat', 'tong_thanh_toan']
      const updatedFields: Record<string, unknown> = {
        ...fields,
        ...Object.fromEntries(numberKeys.map((key) => [key, fields[key] === '' ? null : Number(fields[key])])),
        danh_sach_mat_hang: finalItems,
      }
      if (Object.values(updatedFields).some((value) => typeof value === 'number' && !Number.isFinite(value))) {
        throw new Error('Số tiền phải là giá trị số hợp lệ.')
      }
      await apiRequest(`/api/invoices/${selected.id}`, { method: 'PUT', body: { fields: updatedFields } })
      setNotice({ kind: 'success', text: `Đã lưu dữ liệu hóa đơn #${selected.id}.` })
      await refresh()
    } catch (reason) {
      setNotice({ kind: 'error', text: getErrorMessage(reason) })
    } finally {
      setSaving(false)
    }
  }

  async function updateAccountingStatus(status: Invoice['accounting_status']) {
    if (!selected) return
    try {
      await apiRequest(`/api/invoices/${selected.id}/accounting-status`, { method: 'PUT', body: { status } })
      setNotice({ kind: 'success', text: 'Đã cập nhật trạng thái duyệt hóa đơn.' })
      await refresh()
    } catch (reason) {
      setError(getErrorMessage(reason))
    }
  }

  // Arithmetic validation
  const numGoods = Number(fields.tong_tien_hang) || 0
  const numVat = Number(fields.tien_thue_vat) || 0
  const numTotal = Number(fields.tong_thanh_toan) || 0
  const arithmeticDiff = Math.abs(numGoods + numVat - numTotal)
  const isArithmeticValid = numTotal > 0 && arithmeticDiff <= 1

  return (
    <div className="workspace-content">
      <PageHeading
        eyebrow="AI OCR & DATA INSPECTION STUDIO"
        title="🔬 Trích xuất & Kiểm toán dữ liệu"
        description="Bóc tách chi tiết thông tin hóa đơn, kiểm tra tính toàn vẹn số học và đối soát hóa đơn trùng lặp."
        action={<button className="button subtle" onClick={refresh}>↻ Làm mới</button>}
      />
      {error && <div className="inline-error" role="alert">{error}</div>}
      {!invoices.length ? (
        <section className="workspace-panel">
          <EmptyState
            title="Chưa có hóa đơn để kiểm tra"
            description="Hãy tải hóa đơn lên để hệ thống nhận dạng và trích xuất dữ liệu."
          />
        </section>
      ) : (
        <>
          <section className="workspace-panel selection-panel" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: '300px' }}>
              <label htmlFor="invoice-select" style={{ fontWeight: 700, color: '#334155' }}>Hồ sơ hóa đơn:</label>
              <select
                id="invoice-select"
                onChange={(event) => setSelectedId(Number(event.target.value))}
                value={selectedId ?? ''}
                style={{ flex: 1 }}
              >
                {invoices.map((invoice) => (
                  <option key={invoice.id} value={invoice.id}>
                    DOC-ID #{String(invoice.id).padStart(4, '0')} · {invoice.ten_cong_ty_ban || 'Chưa rõ nhà cung cấp'} · {invoice.so_hoa_don || 'Chưa có số'}
                  </option>
                ))}
              </select>
            </div>
            {selected && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {isAdmin && (selected.uploader_full_name || selected.uploader_username) && (
                  <span className="uploader-pill">👤 {selected.uploader_full_name || selected.uploader_username}</span>
                )}
                <span className={`accounting-pill ${selected.accounting_status}`}>{ACCOUNTING_TITLES[selected.accounting_status]}</span>
              </div>
            )}
          </section>

          {selected && (
            <div className="extract-layout">
              {/* CỘT TRÁI: DOCUMENT PREVIEW HIỂN THỊ RÕ NÉT TRỰC TIẾP */}
              <section className="workspace-panel document-preview">
                <div className="tech-card-header">
                  <div className="tech-card-title">
                    <span>📄</span> Tài liệu nguồn (Original Document)
                  </div>
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    <button
                      type="button"
                      className="button subtle small"
                      onClick={() => {
                        setShowRelink(!showRelink)
                        if (!availableFiles.length) void loadAvailableFiles()
                      }}
                      title="Chọn lại tệp nguồn nếu muốn đổi ảnh"
                    >
                      🔗 {showRelink ? 'Đóng liên kết' : 'Đổi tệp'}
                    </button>
                    <a
                      href={`/api/files/invoices/${selected.id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="button subtle small"
                      title="Mở tài liệu trong tab trình duyệt riêng"
                    >
                      ↗ Mở tab mới
                    </a>
                  </div>
                </div>

                {/* Box chọn liên kết lại tệp khi người dùng cần */}
                {showRelink && (
                  <div className="relink-container" style={{ marginBottom: '14px' }}>
                    <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '6px', display: 'block' }}>
                      Chọn tệp nguồn từ máy chủ ({availableFiles.length} tệp có sẵn):
                    </label>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <select
                        value={relinkPath}
                        onChange={(e) => setRelinkPath(e.target.value)}
                        style={{ flex: 1, padding: '8px 10px', fontSize: '13px', borderRadius: '6px', border: '1px solid #CBD5E1' }}
                      >
                        <option value="">-- Chọn tệp trên máy chủ --</option>
                        {availableFiles.map((file) => (
                          <option key={file.path} value={file.path}>
                            [{file.folder}] {file.name} ({(file.size / 1024).toFixed(1)} KB)
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className="button primary small"
                        disabled={!relinkPath || relinking}
                        onClick={handleRelinkSource}
                      >
                        {relinking ? 'Đang lưu...' : 'Lưu'}
                      </button>
                    </div>
                  </div>
                )}

                {/* KHUNG HIỂN THỊ HÓA ĐƠN TRỰC TIẾP */}
                {isPdf ? (
                  <iframe
                    key={`pdf-${selected.id}`}
                    title={`Tài liệu hóa đơn ${selected.id}`}
                    src={`/api/files/invoices/${selected.id}`}
                    className="document-preview-iframe"
                  />
                ) : (
                  <div className="doc-image-viewport">
                    <img
                      key={`img-${selected.id}`}
                      src={`/api/files/invoices/${selected.id}`}
                      alt={`Hóa đơn #${selected.id}`}
                      className="doc-rendered-image"
                    />
                  </div>
                )}

                <div className="doc-meta-bar">
                  <span title={selected.source_image ?? ''}>
                    📁 <strong>{selected.source_image ? selected.source_image.split(/[\\/]/).pop() : 'Chưa có tệp'}</strong>
                  </span>
                  <span>DOC-ID: <strong>#{String(selected.id).padStart(4, '0')}</strong></span>
                </div>
              </section>

              {/* CỘT PHẢI: BÓC TÁCH DỮ LIỆU & KIỂM TOÁN */}
              <section className="workspace-panel extract-editor">
                <div className="tech-card-header">
                  <div className="tech-card-title">
                    <span>🤖</span> Bóc tách AI &amp; Kiểm toán (Audit Inspector)
                  </div>
                  <span className="tech-card-tag">SCHEMA V2.0</span>
                </div>

                {isArithmeticValid ? (
                  <div className="success-notice" style={{ marginBottom: '14px' }}>
                    ✅ <strong>Kiểm toán số học hoàn tất:</strong> Tiền hàng + Thuế VAT khớp hoàn toàn với Tổng thanh toán.
                  </div>
                ) : numTotal > 0 ? (
                  <div className="warn-notice" style={{ marginBottom: '14px' }}>
                    ⚠️ <strong>Cần đối soát số học:</strong> Tiền hàng ({formatCurrency(numGoods)}) + Thuế VAT ({formatCurrency(numVat)}) chưa khớp Tổng thanh toán ({formatCurrency(numTotal)}).
                  </div>
                ) : null}

                <form onSubmit={saveInvoice}>
                  <div style={{ fontWeight: 700, color: '#1E293B', fontSize: '13px', margin: '4px 0 2px' }}>
                    🏢 Thông tin đối tác bên bán &amp; bên mua
                  </div>
                  <div className="invoice-fields">
                    <label>
                      <span>Tên công ty bên bán</span>
                      <input
                        disabled={!canEdit}
                        onChange={(e) => setFields((v) => ({ ...v, ten_cong_ty_ban: e.target.value }))}
                        value={fields.ten_cong_ty_ban ?? ''}
                      />
                    </label>
                    <label>
                      <span>Mã số thuế bên bán</span>
                      <input
                        disabled={!canEdit}
                        onChange={(e) => setFields((v) => ({ ...v, ma_so_thue_ban: e.target.value }))}
                        value={fields.ma_so_thue_ban ?? ''}
                      />
                    </label>
                    <label>
                      <span>Tên công ty bên mua</span>
                      <input
                        disabled={!canEdit}
                        onChange={(e) => setFields((v) => ({ ...v, ten_cong_ty_mua: e.target.value }))}
                        value={fields.ten_cong_ty_mua ?? ''}
                      />
                    </label>
                    <label>
                      <span>Mã số thuế bên mua</span>
                      <input
                        disabled={!canEdit}
                        onChange={(e) => setFields((v) => ({ ...v, ma_so_thue_mua: e.target.value }))}
                        value={fields.ma_so_thue_mua ?? ''}
                      />
                    </label>
                  </div>

                  <div style={{ fontWeight: 700, color: '#1E293B', fontSize: '13px', margin: '14px 0 2px' }}>
                    📑 Chi tiết chứng từ hóa đơn
                  </div>
                  <div className="invoice-fields">
                    <label>
                      <span>Số hóa đơn</span>
                      <input
                        disabled={!canEdit}
                        onChange={(e) => setFields((v) => ({ ...v, so_hoa_don: e.target.value }))}
                        value={fields.so_hoa_don ?? ''}
                      />
                    </label>
                    <label>
                      <span>Ngày lập</span>
                      <input
                        disabled={!canEdit}
                        onChange={(e) => setFields((v) => ({ ...v, ngay_lap: e.target.value }))}
                        value={fields.ngay_lap ?? ''}
                      />
                    </label>
                    <label>
                      <span>Thuế suất VAT (%)</span>
                      <input
                        disabled={!canEdit}
                        onChange={(e) => setFields((v) => ({ ...v, thue_suat_vat: e.target.value }))}
                        value={fields.thue_suat_vat ?? ''}
                      />
                    </label>
                  </div>

                  {/* BẢNG DANH MỤC CHI TIẾT MẶT HÀNG — THIẾT KẾ ĐẸP, VỪA VẶN, KHÔNG THANH TRƯỢT */}
                  <div className="items-table-card">
                    <div className="items-table-header">
                      <div className="items-title-group">
                        <div className="items-icon-badge">📦</div>
                        <div className="items-main-title">
                          Danh mục hàng hóa &amp; dịch vụ
                          <span className="items-count-pill">{items.length} mặt hàng</span>
                        </div>
                      </div>
                      {canEdit && (
                        <button
                          type="button"
                          className="add-item-btn"
                          onClick={addItemRow}
                          title="Thêm một mặt hàng mới vào danh sách"
                        >
                          ＋ Thêm dòng
                        </button>
                      )}
                    </div>

                    <div className="items-table-wrapper">
                      <table className="items-table">
                        <thead>
                          <tr>
                            <th style={{ width: '32px', textAlign: 'center' }}>#</th>
                            <th>Tên hàng hóa / dịch vụ</th>
                            <th style={{ width: '55px', textAlign: 'center' }}>ĐVT</th>
                            <th style={{ width: '60px', textAlign: 'right' }}>SL</th>
                            <th style={{ width: '105px', textAlign: 'right' }}>Đơn giá (đ)</th>
                            <th style={{ width: '115px', textAlign: 'right' }}>Thành tiền (đ)</th>
                            {canEdit && <th style={{ width: '34px', textAlign: 'center' }}></th>}
                          </tr>
                        </thead>
                        <tbody>
                          {items.length === 0 ? (
                            <tr>
                              <td
                                colSpan={canEdit ? 7 : 6}
                                style={{ textAlign: 'center', padding: '28px 16px', color: '#94A3B8' }}
                              >
                                Chưa có mặt hàng nào. Nhấn <strong>"＋ Thêm dòng"</strong> để thêm hàng hóa bóc tách.
                              </td>
                            </tr>
                          ) : (
                            items.map((item, idx) => (
                              <tr key={item.id}>
                                <td style={{ textAlign: 'center', fontWeight: 600, color: '#64748B' }}>
                                  {idx + 1}
                                </td>
                                <td>
                                  <input
                                    type="text"
                                    value={item.ten_hang}
                                    onChange={(e) => updateItem(idx, 'ten_hang', e.target.value)}
                                    disabled={!canEdit}
                                    placeholder="Tên sản phẩm, dịch vụ..."
                                    className="item-cell-input"
                                  />
                                </td>
                                <td>
                                  <input
                                    type="text"
                                    value={item.don_vi_tinh}
                                    onChange={(e) => updateItem(idx, 'don_vi_tinh', e.target.value)}
                                    disabled={!canEdit}
                                    placeholder="Cái, kg"
                                    className="item-cell-input unit"
                                  />
                                </td>
                                <td>
                                  <input
                                    type="number"
                                    value={item.so_luong}
                                    onChange={(e) => updateItem(idx, 'so_luong', e.target.value)}
                                    disabled={!canEdit}
                                    placeholder="0"
                                    className="item-cell-input qty"
                                  />
                                </td>
                                <td>
                                  <input
                                    type="number"
                                    value={item.don_gia}
                                    onChange={(e) => updateItem(idx, 'don_gia', e.target.value)}
                                    disabled={!canEdit}
                                    placeholder="0"
                                    className="item-cell-input amount"
                                  />
                                </td>
                                <td>
                                  <input
                                    type="number"
                                    value={item.thanh_tien}
                                    onChange={(e) => updateItem(idx, 'thanh_tien', e.target.value)}
                                    disabled={!canEdit}
                                    placeholder="0"
                                    className="item-cell-input amount"
                                  />
                                </td>
                                {canEdit && (
                                  <td style={{ textAlign: 'center' }}>
                                    <button
                                      type="button"
                                      onClick={() => removeItemRow(idx)}
                                      title="Xóa dòng này"
                                      className="btn-delete-row"
                                    >
                                      ✕
                                    </button>
                                  </td>
                                )}
                              </tr>
                            ))
                          )}
                        </tbody>
                        {items.length > 0 && (
                          <tfoot>
                            <tr>
                              <td colSpan={3} style={{ fontWeight: 700, color: '#1E293B', padding: '10px 10px' }}>
                                Tổng cộng ({items.length} mặt hàng)
                              </td>
                              <td style={{ textAlign: 'right', fontWeight: 700, color: '#0F172A', padding: '10px 6px' }}>
                                {totalQuantity.toLocaleString('vi-VN')}
                              </td>
                              <td></td>
                              <td style={{ textAlign: 'right', fontWeight: 700, color: '#1E40AF', fontSize: '13px', padding: '10px 6px' }}>
                                {formatCurrency(totalCalculatedGoods)}
                              </td>
                              {canEdit && (
                                <td style={{ textAlign: 'center', padding: '6px 2px' }}>
                                  {totalCalculatedGoods > 0 && Math.abs(totalCalculatedGoods - numGoods) > 1 && (
                                    <button
                                      type="button"
                                      title="Đồng bộ tổng thành tiền này vào ô Tiền hàng bên dưới"
                                      className="btn-sync-amount"
                                      onClick={syncTotalToGoods}
                                    >
                                      ⚡ Đồng bộ
                                    </button>
                                  )}
                                </td>
                              )}
                            </tr>
                          </tfoot>
                        )}
                      </table>
                    </div>
                  </div>

                  <div style={{ fontWeight: 700, color: '#1E293B', fontSize: '13px', margin: '14px 0 2px' }}>
                    💰 Tổng kết số liệu tài chính
                  </div>
                  <div className="invoice-fields">
                    <label>
                      <span>Tiền hàng (chưa VAT)</span>
                      <input
                        disabled={!canEdit}
                        onChange={(e) => setFields((v) => ({ ...v, tong_tien_hang: e.target.value }))}
                        type="number"
                        value={fields.tong_tien_hang ?? ''}
                      />
                    </label>
                    <label>
                      <span>Tiền thuế VAT</span>
                      <input
                        disabled={!canEdit}
                        onChange={(e) => setFields((v) => ({ ...v, tien_thue_vat: e.target.value }))}
                        type="number"
                        value={fields.tien_thue_vat ?? ''}
                      />
                    </label>
                    <label>
                      <span>Tổng thanh toán</span>
                      <input
                        disabled={!canEdit}
                        onChange={(e) => setFields((v) => ({ ...v, tong_thanh_toan: e.target.value }))}
                        type="number"
                        value={fields.tong_thanh_toan ?? ''}
                      />
                    </label>
                  </div>

                  <div className="finance-summary-grid">
                    <div className="finance-cell">
                      <div className="finance-cell-label">Tiền hàng</div>
                      <div className="finance-cell-value">{formatCurrency(numGoods)}</div>
                    </div>
                    <div className="finance-cell">
                      <div className="finance-cell-label">Thuế VAT</div>
                      <div className="finance-cell-value">{formatCurrency(numVat)}</div>
                    </div>
                    <div className="finance-cell">
                      <div className="finance-cell-label">Tổng thanh toán</div>
                      <div className="finance-cell-value highlight">{formatCurrency(numTotal)}</div>
                    </div>
                  </div>

                  {!canEdit && (
                    <p className="soft-note">
                      Hóa đơn đã được quản trị viên duyệt/từ chối. Liên hệ Admin nếu cần mở lại để chỉnh sửa.
                    </p>
                  )}

                  <div className="editor-actions">
                    <button className="button primary" disabled={saving || !canEdit} type="submit">
                      {saving ? 'Đang lưu...' : '💾 Lưu thay đổi thông tin'}
                    </button>
                    {isAdmin && (
                      <div style={{ display: 'flex', gap: '8px', marginLeft: 'auto' }}>
                        <button
                          className="button primary"
                          disabled={selected.accounting_status === 'confirmed'}
                          onClick={() => void updateAccountingStatus('confirmed')}
                          type="button"
                          style={{ background: '#10B981' }}
                        >
                          ✅ Duyệt hóa đơn
                        </button>
                        <button
                          className="button danger-outline"
                          disabled={selected.accounting_status === 'rejected'}
                          onClick={() => void updateAccountingStatus('rejected')}
                          type="button"
                        >
                          ❌ Từ chối
                        </button>
                      </div>
                    )}
                  </div>
                </form>
              </section>
            </div>
          )}
        </>
      )}
    </div>
  )
}
