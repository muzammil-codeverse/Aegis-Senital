import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AlertCard from './AlertCard'

describe('AlertCard', () => {
  it('shows uploaded-video source metadata and links back to the report page', () => {
    window.location.hash = ''
    render(
      <AlertCard
        alert={{
          alert_id: 'alert-uv-demo',
          severity: 'high',
          state: 'new',
          title: 'HIGH uploaded-video weapon detected',
          description: 'Operator review required.',
          risk_score: 0.9,
          confidence: 0.84,
          camera_ids: ['uploaded:uvs_demo'],
          track_ids: [],
          metadata: {
            uploaded_video: {
              session_id: 'uvs_demo',
              original_filename: 'demo.avi',
              frame_index: 3,
            },
          },
        }}
        selected={false}
        onSelect={vi.fn()}
      />,
    )

    expect(screen.getByText('Uploaded video')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /open report/i }))
    expect(window.location.hash).toBe('#uploaded-video-analysis')
  })
})
