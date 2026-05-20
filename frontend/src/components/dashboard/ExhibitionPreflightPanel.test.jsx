import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ExhibitionPreflightPanel from './ExhibitionPreflightPanel'

describe('ExhibitionPreflightPanel', () => {
  it('renders no-run state', () => {
    render(<ExhibitionPreflightPanel latestRun={{ overall_status: 'NOT_STARTED', results: [] }} summary={{ by_state: {} }} />)

    expect(screen.getByText('Exhibition Preflight')).toBeInTheDocument()
    expect(screen.getByText('Core capability awaiting preflight.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run quick/i })).toBeInTheDocument()
  })

  it('renders degraded OpenAI provider warning', () => {
    render(
      <ExhibitionPreflightPanel
        latestRun={{
          overall_status: 'PARTIALLY_PASSED',
          results: [
            {
              capability_id: 'llm_osint',
              name: 'LLM / OSINT',
              group: 'ADVANCED_INTELLIGENCE',
              state: 'DEGRADED',
              check_level: 2,
              reason: 'OPENAI_API_KEY missing',
              metadata: { openai_key_present: false },
              recommendations: ['Set OPENAI_API_KEY in the backend-loaded local env file.'],
            },
          ],
          warnings: ['llm_osint: Provider key missing'],
          recommendations: [],
        }}
        summary={{ by_state: { DEGRADED: 1 } }}
      />,
    )

    expect(screen.getByText(/OPENAI_API_KEY is absent/i)).toBeInTheDocument()
    expect(screen.getByText(/OSINT \/ LLM enrichment provider not configured/i)).toBeInTheDocument()
  })

  it('calls run actions', () => {
    const runQuick = vi.fn()
    const runExhibition = vi.fn()
    render(
      <ExhibitionPreflightPanel
        latestRun={{ overall_status: 'NOT_STARTED', results: [] }}
        summary={{ by_state: {} }}
        onRunQuick={runQuick}
        onRunExhibition={runExhibition}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /run quick/i }))
    fireEvent.click(screen.getByRole('button', { name: /run exhibition/i }))

    expect(runQuick).toHaveBeenCalledTimes(1)
    expect(runExhibition).toHaveBeenCalledTimes(1)
  })
})

