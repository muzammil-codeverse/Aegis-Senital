import { render } from '@testing-library/react'

export function renderWithProviders(ui, options = {}) {
  return render(ui, options)
}
