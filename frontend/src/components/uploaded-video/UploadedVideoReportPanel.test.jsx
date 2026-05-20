import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import UploadedVideoReportPanel from './UploadedVideoReportPanel'

describe('UploadedVideoReportPanel', () => {
  it('renders detection summary from the uploaded-video report contract', () => {
    render(
      <UploadedVideoReportPanel
        report={{
          video_metadata: { original_filename: 'demo.avi', frames_processed: 4 },
          integrity: { status: 'verified' },
          models_used: [{ model_id: 'weapon_yolo11s_v2_current' }],
          detections_summary: {
            total_events: 2,
            detected_classes: ['weapon_detected', 'phone_detected'],
            event_types: { weapon_detected: 1, phone_detected: 1 },
            confidence_summary: { max: 0.91, average: 0.82 },
          },
          model_caveats: ['Operator review required.'],
          chain_of_custody: {},
          replay_summary: {},
          replay_clips: [],
        }}
      />,
    )

    expect(screen.getByText('Detection Summary')).toBeInTheDocument()
    expect(screen.getByText('weapon_detected, phone_detected')).toBeInTheDocument()
    expect(screen.getByText('weapon_detected: 1')).toBeInTheDocument()
  })

  it('states when completed processing found no detections', () => {
    render(
      <UploadedVideoReportPanel
        report={{
          video_metadata: { original_filename: 'empty.avi', frames_processed: 4 },
          integrity: { status: 'verified' },
          models_used: [],
          detections_summary: { total_events: 0, event_types: {}, confidence_summary: {} },
          model_caveats: [],
          chain_of_custody: {},
          replay_summary: {},
          replay_clips: [],
        }}
      />,
    )

    expect(screen.getByText('No detections found.')).toBeInTheDocument()
  })

  it('shows command-center alert and evidence linkage when present', () => {
    render(
      <UploadedVideoReportPanel
        report={{
          video_metadata: { original_filename: 'linked.avi', frames_processed: 4 },
          integrity: { status: 'verified' },
          models_used: [],
          detections_summary: { total_events: 1, event_types: { weapon_detected: 1 }, confidence_summary: {} },
          model_caveats: [],
          chain_of_custody: {},
          replay_summary: {},
          replay_clips: [],
          metadata: {
            command_center: {
              status: 'promoted',
              alert_ids: ['alert-uv-demo'],
              incident_ids: ['inc-uv-demo'],
              evidence_refs: ['uploaded_video:demo:report'],
            },
          },
        }}
      />,
    )

    expect(screen.getByText('Command-Center Linkage')).toBeInTheDocument()
    expect(screen.getByText('alert-uv-demo')).toBeInTheDocument()
    expect(screen.getByText('Open Alerts')).toBeInTheDocument()
  })
})
