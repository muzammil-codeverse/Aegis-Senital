import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import LoginPage from './LoginPage'

const login = vi.fn()

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    login,
    loading: false,
    error: null,
  }),
}))

describe('LoginPage', () => {
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
})
