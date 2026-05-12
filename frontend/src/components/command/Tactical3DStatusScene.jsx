import { useEffect, useMemo, useState } from 'react'

function ReducedMotionFallback({ summary }) {
  return (
    <div className="tactical-3d-fallback">
      <div className="tactical-3d-fallback__grid" />
      <div className="tactical-3d-fallback__content">
        <p className="eyebrow">Tactical 3D</p>
        <h3>Network status scene</h3>
        <p>{summary}</p>
      </div>
    </div>
  )
}

function StaticScene() {
  const nodes = [
    { position: [-1.8, 0.8, 0], color: '#5bc0eb' },
    { position: [0, 1.2, 0], color: '#f2c14e' },
    { position: [1.6, 0.2, 0], color: '#4ade80' },
    { position: [-0.4, -1.2, 0], color: '#fb7185' },
    { position: [1.1, -1.1, 0], color: '#60a5fa' },
  ]
  const lines = [
    [[-1.8, 0.8, 0], [0, 1.2, 0]],
    [[0, 1.2, 0], [1.6, 0.2, 0]],
    [[0, 1.2, 0], [-0.4, -1.2, 0]],
    [[1.6, 0.2, 0], [1.1, -1.1, 0]],
  ]

  return (
    <>
      <ambientLight intensity={0.65} />
      <pointLight position={[4, 4, 4]} intensity={6} />
      {nodes.map((node, index) => (
        <mesh key={index} position={node.position}>
          <sphereGeometry args={[0.18, 24, 24]} />
          <meshStandardMaterial color={node.color} emissive={node.color} emissiveIntensity={0.4} />
        </mesh>
      ))}
      {lines.map((line, index) => (
        <line key={index}>
          <bufferGeometry>
            <bufferAttribute
              attach="attributes-position"
              args={[new Float32Array([...line[0], ...line[1]]), 3]}
            />
          </bufferGeometry>
          <lineBasicMaterial color="#7dd3fc" />
        </line>
      ))}
    </>
  )
}

export default function Tactical3DStatusScene({ summary = 'Abstract camera, drone, and fusion network overview.' }) {
  const reducedMotion = useMemo(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  )
  const [Canvas, setCanvas] = useState(null)

  useEffect(() => {
    if (reducedMotion) return undefined
    let cancelled = false
    const timer = window.setTimeout(() => {
      import('@react-three/fiber')
        .then(module => {
          if (!cancelled) setCanvas(() => module.Canvas)
        })
        .catch(() => {
          if (!cancelled) setCanvas(null)
        })
    }, 10)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [reducedMotion])

  if (reducedMotion || !Canvas) {
    return <ReducedMotionFallback summary={summary} />
  }

  return (
    <div className="tactical-3d-scene">
      <Canvas camera={{ position: [0, 0, 5], fov: 40 }} dpr={[1, 1.5]} frameloop="demand">
        <StaticScene />
      </Canvas>
      <div className="tactical-3d-scene__caption">
        <p className="eyebrow">Tactical 3D</p>
        <p>{summary}</p>
      </div>
    </div>
  )
}
