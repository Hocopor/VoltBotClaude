import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Zap } from 'lucide-react'

import { authApi } from '../api'
import { useStore } from '../store'


export default function Login() {
  const navigate = useNavigate()
  const setAppSession = useStore((s) => s.setAppSession)
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    try {
      const response = await authApi.login({ login, password })
      setAppSession({ authenticated: true, login: response.data.login })
      toast.success('Logged in')
      navigate('/', { replace: true })
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-voltage-bg flex items-center justify-center p-6">
      <div className="w-full max-w-md panel p-8">
        <div className="flex items-center gap-3 mb-6">
          <Zap size={24} className="text-voltage-accent" fill="currentColor" />
          <div>
            <div className="text-xl font-bold tracking-widest text-voltage-accent font-mono">VOLTAGE</div>
            <div className="text-xs text-voltage-muted tracking-wider">AUTHORIZED ACCESS ONLY</div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label>Login</label>
            <input
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          <button type="submit" className="btn-primary w-full" disabled={submitting}>
            {submitting ? 'Signing In...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
