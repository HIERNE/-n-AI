import { useEffect, useState, type FormEvent } from 'react'
import './App.css'
import { ApiError, apiRequest, type User } from './api'
import { Workspace } from './Workspace'

type AuthMode = 'login' | 'register'

function BrandMark({ className = '' }: { className?: string }) {
  return <img className={`brand-mark ${className}`} src="/invoiceai_logo.png" alt="Invoice Pro" />
}

function AuthPage({ onLogin }: { onLogin: (user: User) => void }) {
  const [currentYear] = useState(() => new Date().getFullYear())
  const [mode, setMode] = useState<AuthMode>('login')
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(true)
  const [agreed, setAgreed] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showTerms, setShowTerms] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setNotice('')

    if (mode === 'register') {
      if (password !== confirmPassword) {
        setError('Mật khẩu xác nhận không khớp.')
        return
      }
      if (!agreed) {
        setError('Vui lòng đồng ý với Điều khoản sử dụng và Chính sách bảo mật.')
        return
      }
    }

    setBusy(true)
    try {
      if (mode === 'login') {
        const result = await apiRequest<{ user: User }>('/api/auth/login', {
          body: { username: email.trim(), password, remember_me: rememberMe },
        })
        onLogin(result.user)
      } else {
        const result = await apiRequest<{ message: string }>('/api/auth/register', {
          body: { full_name: fullName.trim(), email: email.trim(), password },
        })
        setMode('login')
        setPassword('')
        setConfirmPassword('')
        setNotice(result.message)
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Đã xảy ra lỗi.')
    } finally {
      setBusy(false)
    }
  }

  function changeMode(nextMode: AuthMode) {
    setMode(nextMode)
    setError('')
    setNotice('')
    setPassword('')
    setConfirmPassword('')
  }

  return (
    <main className="auth-layout">
      <section className="hero-panel" aria-label="Invoice Pro">
        <div className="hero-glow hero-glow-one" />
        <div className="hero-glow hero-glow-two" />
        <div className="hero-content">
          <a className="brand-lockup" href="/" aria-label="Invoice Pro - Trang chủ">
            <BrandMark />
            <span>Invoice Pro</span>
          </a>

          <div className="hero-copy">
            <div className="hero-eyebrow"><span /> NỀN TẢNG HÓA ĐƠN THÔNG MINH</div>
            <h1>Quản lý hóa đơn<br />nhẹ nhàng hơn.</h1>
            <p>
              Tự động hóa quy trình nhập liệu, lưu trữ và theo dõi hóa đơn của
              doanh nghiệp trên một nền tảng bảo mật.
            </p>
            <div className="feature-list">
              <div><span className="feature-icon">⚡</span><span>Trích xuất dữ liệu bằng AI trong vài giây</span></div>
              <div><span className="feature-icon">🛡️</span><span>Dữ liệu được mã hóa và bảo mật</span></div>
              <div><span className="feature-icon">📊</span><span>Theo dõi chi phí trực quan, chính xác</span></div>
            </div>
          </div>

          <div className="hero-footer">
            <span className="status-dot" />
            © {currentYear} Invoice Pro · Nền tảng hóa đơn thông minh
          </div>
        </div>
      </section>

      <section className="form-panel">
        <div className="mobile-brand"><BrandMark /><span>Invoice Pro</span></div>
        <div className="auth-card">
          <div className="auth-tabs">
            <button
              className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
              onClick={() => changeMode('login')}
              type="button"
            >
              Đăng nhập
            </button>
            <button
              className={`auth-tab ${mode === 'register' ? 'active' : ''}`}
              onClick={() => changeMode('register')}
              type="button"
            >
              Đăng ký
            </button>
          </div>

          <div className="welcome-label">{mode === 'login' ? 'CHÀO MỪNG TRỞ LẠI' : 'BẮT ĐẦU MIỄN PHÍ'}</div>
          <h2>{mode === 'login' ? 'Chào mừng trở lại' : 'Tạo tài khoản mới'}</h2>
          <p className="form-subtitle">
            {mode === 'login'
              ? 'Đăng nhập để tiếp tục quản lý hóa đơn của bạn.'
              : 'Bắt đầu quản lý hóa đơn chuyên nghiệp ngay hôm nay.'}
          </p>

          {notice && <div className="notice-message" role="status">{notice}</div>}
          {error && <div className="error-message" role="alert">{error}</div>}

          <form onSubmit={handleSubmit}>
            {mode === 'register' && (
              <label className="field">
                <span>Họ và tên</span>
                <input
                  autoComplete="name"
                  maxLength={255}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder="Nguyễn Văn An"
                  required
                  value={fullName}
                />
              </label>
            )}

            <label className="field">
              <span>{mode === 'login' ? 'Email hoặc tên đăng nhập' : 'Email'}</span>
              <input
                autoComplete={mode === 'login' ? 'username' : 'email'}
                maxLength={255}
                onChange={(event) => setEmail(event.target.value)}
                placeholder={mode === 'login' ? 'Email hoặc tài khoản admin' : 'name@gmail.com'}
                required
                type={mode === 'login' ? 'text' : 'email'}
                value={email}
              />
            </label>

            <label className="field">
              <span>Mật khẩu</span>
              <span className="password-input">
                <input
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  maxLength={1024}
                  minLength={mode === 'login' ? 1 : 6}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder={mode === 'login' ? 'Tối thiểu 8 ký tự' : 'Tối thiểu 6 ký tự'}
                  required
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                />
                <button
                  aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                  className="password-toggle"
                  onClick={() => setShowPassword((visible) => !visible)}
                  type="button"
                >
                  {showPassword ? 'Ẩn' : 'Hiện'}
                </button>
              </span>
            </label>

            {mode === 'register' ? (
              <>
                <label className="field">
                  <span>Xác nhận mật khẩu</span>
                  <input
                    autoComplete="new-password"
                    maxLength={1024}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    placeholder="Nhập lại mật khẩu"
                    required
                    type="password"
                    value={confirmPassword}
                  />
                </label>
                <label className="check-row terms-row">
                  <div className="check-row-left">
                    <input checked={agreed} onChange={(event) => setAgreed(event.target.checked)} type="checkbox" />
                    <span>
                      Tôi đồng ý với{' '}
                      <button className="inline-link" onClick={() => setShowTerms(true)} type="button">
                        Điều khoản sử dụng
                      </button>{' '}
                      và{' '}
                      <button className="inline-link" onClick={() => setShowTerms(true)} type="button">
                        Chính sách bảo mật
                      </button>.
                    </span>
                  </div>
                </label>
              </>
            ) : (
              <div className="check-row">
                <label className="check-row-left">
                  <input checked={rememberMe} onChange={(event) => setRememberMe(event.target.checked)} type="checkbox" />
                  <span>Ghi nhớ đăng nhập</span>
                </label>
                <button className="inline-link" onClick={() => alert('Vui lòng liên hệ quản trị viên để đặt lại mật khẩu.')} type="button">
                  Quên mật khẩu?
                </button>
              </div>
            )}

            <button className="submit-button" disabled={busy} type="submit">
              {busy ? 'Đang xử lý...' : mode === 'login' ? 'Đăng nhập' : 'Tạo tài khoản'}
              {!busy && <span aria-hidden="true">→</span>}
            </button>
          </form>

          <div className="auth-switch">
            {mode === 'login' ? 'Chưa có tài khoản?' : 'Đã có tài khoản?'}
            <button
              onClick={() => changeMode(mode === 'login' ? 'register' : 'login')}
              type="button"
            >
              {mode === 'login' ? 'Đăng ký ngay' : 'Đăng nhập'}
            </button>
          </div>
          <div className="security-note"><span>🔒</span> Kết nối an toàn với mã hóa SSL 256-bit</div>
        </div>
        <footer className="form-footer">© {currentYear} Invoice Pro. Bảo lưu mọi quyền.</footer>
        {showTerms && (
          <div className="dialog-backdrop" onClick={() => setShowTerms(false)}>
            <section
              aria-labelledby="terms-title"
              aria-modal="true"
              className="terms-dialog"
              onClick={(event) => event.stopPropagation()}
              role="dialog"
            >
              <button
                aria-label="Đóng điều khoản"
                className="dialog-close"
                onClick={() => setShowTerms(false)}
                type="button"
              >
                ×
              </button>
              <div className="welcome-label">INVOICE PRO</div>
              <h2 id="terms-title">Điều khoản &amp; Chính sách bảo mật</h2>
              <p><strong>Dữ liệu hóa đơn:</strong> Chỉ tài khoản của bạn và quản trị viên được phân quyền mới có thể xem dữ liệu theo vai trò trong ứng dụng.</p>
              <p><strong>Tài khoản:</strong> Bạn chịu trách nhiệm bảo mật thông tin đăng nhập và không chia sẻ mật khẩu cho người khác.</p>
              <p><strong>Quyền riêng tư:</strong> Ứng dụng lưu thông tin tài khoản và hóa đơn để cung cấp các chức năng quản lý, đối soát và báo cáo.</p>
              <button className="submit-button dialog-submit" onClick={() => setShowTerms(false)} type="button">Đã hiểu</button>
            </section>
          </div>
        )}
      </section>
    </main>
  )
}

function App() {
  const [user, setUser] = useState<User | null>(null)
  const [checkingSession, setCheckingSession] = useState(true)
  const [startupError, setStartupError] = useState('')

  useEffect(() => {
    let active = true
    apiRequest<{ user: User }>('/api/auth/me')
      .then(({ user: currentUser }) => {
        if (active) setUser(currentUser)
      })
      .catch((requestError: unknown) => {
        if (active) {
          setUser(null)
          if (!(requestError instanceof ApiError) || requestError.status !== 401) {
            setStartupError('Không kết nối được tới máy chủ. Hãy kiểm tra API rồi thử tải lại trang.')
          }
        }
      })
      .finally(() => {
        if (active) setCheckingSession(false)
      })
    return () => { active = false }
  }, [])

  if (checkingSession) {
    return <main className="loading-screen"><span className="loading-spinner" />Đang kiểm tra phiên đăng nhập...</main>
  }
  if (startupError) {
    return (
      <main className="loading-screen startup-error">
        <p role="alert">{startupError}</p>
        <button className="logout-button" onClick={() => window.location.reload()}>Thử lại</button>
      </main>
    )
  }
  return user
    ? <Workspace onLogout={() => setUser(null)} user={user} />
    : <AuthPage onLogin={setUser} />
}

export default App
