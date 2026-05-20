import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LoginPage from './LoginPage'

const login = vi.fn()
let authState

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => authState,
}))

describe('LoginPage', () => {
  beforeEach(() => {
    login.mockReset()
    login.mockResolvedValue({ username: 'admin' })
    authState = {
      login,
      loading: false,
      error: null,
    }
    window.location.hash = ''
  })

  it('renders without protected dashboard api calls', () => {
    render(<LoginPage />)
    expect(screen.getByText('Operator Login')).toBeInTheDocument()
    expect(login).not.toHaveBeenCalled()
    expect(screen.queryByText(/runtime status/i)).not.toBeInTheDocument()
  })

  it('submits credentials only on explicit form submit', async () => {
    render(<LoginPage />)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'ChangeMe123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(login).toHaveBeenCalledTimes(1)
  })

  it('keeps login enabled when session runtime status is unavailable', () => {
    authState = {
      ...authState,
      error: 'Runtime data temporarily unavailable.',
    }

    render(<LoginPage />)

    expect(screen.getByText(/session status check is temporarily unavailable/i)).toBeInTheDocument()
    expect(screen.queryByText('Runtime data temporarily unavailable.')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled()
  })

  it('navigates out of login after successful sign in', async () => {
    window.location.hash = 'login'
    render(<LoginPage />)

    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'AegisLocalAdmin2026!' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => {
      expect(window.location.hash).toBe('')
    })
  })
})
