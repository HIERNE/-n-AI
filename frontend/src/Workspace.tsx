import { useEffect, useState, type FormEvent } from 'react'
import { apiRequest, getErrorMessage, type User } from './api'
import { AccountingPage } from './page/AccountingPage'
import { DashboardPage } from './page/DashboardPage'
import { ExtractionPage } from './page/ExtractionPage'
import { HistoryPage } from './page/HistoryPage'
import { ReportsPage } from './page/ReportsPage'
import { UploadPage } from './page/UploadPage'
import { ErrorNotice, type Notice, type Screen } from './page/shared'
import './Workspace.css'

const NAV_ITEMS: { id: Screen; title: string; icon: string; adminOnly?: boolean }[] = [
  { id: 'dashboard', title: 'Tổng quan', icon: '⌂' },
  { id: 'upload', title: 'Tải hóa đơn', icon: '↑' },
  { id: 'history', title: 'Lịch sử hóa đơn', icon: '◷' },
  { id: 'extract', title: 'Trích xuất dữ liệu', icon: '▤' },
  { id: 'accounting', title: 'Hạch toán kế toán', icon: '∑', adminOnly: true },
  { id: 'reports', title: 'Báo cáo tổng hợp', icon: '▥' },
]

function PasswordDialog({ onClose, setNotice }: {
  onClose: () => void
  setNotice: (notice: Notice) => void
}) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (newPassword !== confirmPassword) { setError('Mật khẩu xác nhận không khớp.'); return }
    setSaving(true)
    setError('')
    try {
      const result = await apiRequest<{ message: string }>('/api/auth/change-password', {
        body: { current_password: currentPassword, new_password: newPassword },
      })
      setNotice({ kind: 'success', text: result.message })
      onClose()
    } catch (reason) { setError(getErrorMessage(reason)) }
    finally { setSaving(false) }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <section aria-labelledby="password-title" aria-modal="true" className="confirm-dialog password-dialog" onClick={(event) => event.stopPropagation()} role="dialog">
        <button aria-label="Đóng" className="dialog-close" onClick={onClose}>×</button>
        <h2 id="password-title">Đổi mật khẩu tài khoản</h2>
        <form onSubmit={submit}>
          <label>Mật khẩu hiện tại<input autoComplete="current-password" onChange={(event) => setCurrentPassword(event.target.value)} required type="password" value={currentPassword} /></label>
          <label>Mật khẩu mới<input autoComplete="new-password" minLength={6} onChange={(event) => setNewPassword(event.target.value)} required type="password" value={newPassword} /></label>
          <label>Xác nhận mật khẩu mới<input autoComplete="new-password" onChange={(event) => setConfirmPassword(event.target.value)} required type="password" value={confirmPassword} /></label>
          {error && <p className="inline-error" role="alert">{error}</p>}
          <button className="button primary full-width" disabled={saving} type="submit" style={{ marginTop: '6px' }}>{saving ? 'Đang cập nhật...' : 'Cập nhật mật khẩu'}</button>
        </form>
      </section>
    </div>
  )
}

export function Workspace({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [loggingOut, setLoggingOut] = useState(false)
  const initialScreen = (): Screen => {
    const path = window.location.pathname.replace(/^\//, '') as Screen
    return NAV_ITEMS.some((item) => item.id === path && (!item.adminOnly || user.role === 'admin')) ? path : 'dashboard'
  }
  const [screen, setScreen] = useState<Screen>(initialScreen)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const updateLocation = () => {
      const path = window.location.pathname.replace(/^\//, '') as Screen
      setScreen(NAV_ITEMS.some((item) => item.id === path && (!item.adminOnly || user.role === 'admin')) ? path : 'dashboard')
    }
    window.addEventListener('popstate', updateLocation)
    return () => window.removeEventListener('popstate', updateLocation)
  }, [user.role])

  function navigate(nextScreen: Screen) {
    if (nextScreen === 'accounting' && user.role !== 'admin') return
    window.history.pushState({}, '', `/${nextScreen}`)
    setScreen(nextScreen)
    setMenuOpen(false)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function logout() {
    setLoggingOut(true)
    try {
      await apiRequest('/api/auth/logout', { body: {} })
      onLogout()
    } catch (reason) {
      setNotice({ kind: 'error', text: getErrorMessage(reason) })
    } finally {
      setLoggingOut(false)
    }
  }

  function openPasswordDialog() {
    setPasswordOpen(true)
    setMenuOpen(false)
  }

  const titles: Record<Screen, string> = {
    dashboard: 'Tổng quan',
    upload: 'Tải hóa đơn',
    history: 'Lịch sử hóa đơn',
    extract: 'Trích xuất dữ liệu',
    accounting: 'Hạch toán kế toán',
    reports: 'Báo cáo tổng hợp',
  }

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <a className="sidebar-brand" href="/upload" onClick={(event) => { event.preventDefault(); navigate('upload') }}>
          <img src="/invoiceai_logo.png" alt="Invoice Pro" />
          <div className="sidebar-brand-text">
            <strong>Invoice Pro</strong>
            <small>Nền tảng hóa đơn thông minh</small>
          </div>
        </a>
        <div className="sidebar-label">KHÔNG GIAN LÀM VIỆC</div>
        <nav aria-label="Điều hướng chính">
          {NAV_ITEMS.filter((item) => !item.adminOnly || user.role === 'admin').map((item) => (
            <button className={`nav-item ${screen === item.id ? 'active' : ''}`} key={item.id} onClick={() => navigate(item.id)}>
              <span>{item.icon}</span>{item.title}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-user">
            <span className="sidebar-avatar">{(user.full_name || user.username).slice(0, 1).toUpperCase()}</span>
            <div className="sidebar-user-info">
              <strong>{user.full_name || user.username}</strong>
              <small>{user.role === 'admin' ? 'Quản trị viên (Admin)' : 'Thành viên'}</small>
            </div>
          </div>
          <button className="sidebar-menu-btn" onClick={() => setMenuOpen((open) => !open)}>
            <span>Tài khoản</span>
            <span>▾</span>
          </button>
          {menuOpen && (
            <div className="account-menu">
              <button onClick={openPasswordDialog}>🔒 Đổi mật khẩu</button>
              <button disabled={loggingOut} onClick={() => void logout()}>{loggingOut ? 'Đang đăng xuất...' : '🚪 Đăng xuất'}</button>
            </div>
          )}
        </div>
      </aside>
      <main className="app-main">
        <header className="topbar">
          <button aria-label="Mở điều hướng" className="mobile-menu" onClick={() => setMenuOpen((open) => !open)}>☰</button>
          <div className="breadcrumb">Không gian làm việc <span>/</span> <strong>{titles[screen]}</strong></div>
          <div className="topbar-user">
            <span className="online-indicator" />
            <span>{user.full_name || user.username}</span>
            <b>{user.role === 'admin' ? 'ADMIN' : 'USER'}</b>
          </div>
        </header>
        {menuOpen && (
          <nav aria-label="Điều hướng di động" className="mobile-nav">
            {NAV_ITEMS.filter((item) => !item.adminOnly || user.role === 'admin').map((item) => (
              <button key={item.id} onClick={() => navigate(item.id)}>{item.icon} {item.title}</button>
            ))}
            <button onClick={openPasswordDialog}>🔒 Đổi mật khẩu</button>
            <button disabled={loggingOut} onClick={() => void logout()}>{loggingOut ? 'Đang đăng xuất...' : '🚪 Đăng xuất'}</button>
          </nav>
        )}
        <ErrorNotice notice={notice} onDismiss={() => setNotice(null)} />
        {screen === 'dashboard' && <DashboardPage navigate={navigate} user={user} />}
        {screen === 'history' && <HistoryPage setNotice={setNotice} user={user} />}
        {screen === 'extract' && <ExtractionPage setNotice={setNotice} user={user} />}
        {screen === 'accounting' && user.role === 'admin' && <AccountingPage setNotice={setNotice} />}
        {screen === 'reports' && <ReportsPage user={user} />}
        {screen === 'upload' && <div className="upload-screen"><UploadPage setNotice={setNotice} /></div>}
      </main>
      {passwordOpen && <PasswordDialog onClose={() => setPasswordOpen(false)} setNotice={setNotice} />}
    </div>
  )
}
