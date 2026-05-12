export default function PathHypothesisTimeline({ steps = [] }) {
  if (!steps.length) {
    return <p className="text-xs text-gray-400">No steps recorded.</p>
  }

  return (
    <ol className="relative border-l border-gray-200 pl-4 text-xs">
      {steps.map(step => (
        <li key={step.step_index} className="mb-4">
          <span className="absolute -left-1.5 mt-0.5 h-3 w-3 rounded-full border border-white bg-blue-500" />
          <div className="font-medium text-gray-800">
            Step {step.step_index + 1} - {step.camera_name || step.camera_id}
            {step.low_confidence_transition ? (
              <span className="ml-2 rounded bg-yellow-100 px-1 py-0.5 text-yellow-700">
                low-confidence transition
              </span>
            ) : null}
            {step.step_type === 'drone_observation' ? (
              <span className="ml-2 rounded bg-amber-100 px-1 py-0.5 text-amber-800">
                simulated aerial step
              </span>
            ) : null}
          </div>
          <div className="text-gray-500">{step.timestamp}</div>
          {step.safe_label ? (
            <div className="text-gray-400">{step.safe_label}</div>
          ) : null}
          {step.event_id ? (
            <div className="text-gray-400">Event: {step.event_id}</div>
          ) : null}
          {step.altitude_meters != null ? (
            <div className="text-gray-400">Altitude: {step.altitude_meters} m</div>
          ) : null}
          {step.travel_seconds_from_prev != null ? (
            <div className="text-gray-400">
              ~{Math.round(step.travel_seconds_from_prev)}s travel from previous
            </div>
          ) : null}
        </li>
      ))}
    </ol>
  )
}
