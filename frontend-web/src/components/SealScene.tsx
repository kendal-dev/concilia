import { Canvas, useFrame, useLoader } from '@react-three/fiber'
import { useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'

import emblem from '../assets/brand/concilia-emblem.png'
import type { Verdict } from '../api/types'

type SealPhase = 'idle' | 'analyzing' | Verdict

interface SealSceneProps {
  phase: SealPhase
}

function useCompactViewport() {
  const [compact, setCompact] = useState(() => window.matchMedia('(max-width: 760px)').matches)

  useEffect(() => {
    const media = window.matchMedia('(max-width: 760px)')
    const update = () => setCompact(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  return compact
}

function Seal({ phase }: SealSceneProps) {
  const group = useRef<THREE.Group>(null)
  const texture = useLoader(THREE.TextureLoader, emblem)

  const targetRotation = phase === 'analyzing' ? Math.PI * 2.1 : phase === 'MISMATCH' ? -0.28 : 0.18
  const bronze = phase === 'MISMATCH' ? '#bb735a' : phase === 'UNCERTAIN' || phase === 'NO_PO_FOUND' ? '#c7974d' : '#b47a3b'

  useFrame((state, delta) => {
    if (!group.current) return
    const pointerTilt = state.pointer.x * 0.12
    group.current.rotation.y = THREE.MathUtils.damp(group.current.rotation.y, targetRotation + pointerTilt, 3, delta)
    group.current.rotation.x = THREE.MathUtils.damp(group.current.rotation.x, state.pointer.y * -0.08, 3, delta)
    group.current.position.y = Math.sin(state.clock.elapsedTime * (phase === 'analyzing' ? 2.4 : 1.15)) * 0.1
  })

  return (
    <group ref={group}>
      <mesh position={[0, 0, -0.05]} castShadow receiveShadow>
        <circleGeometry args={[1.34, 72]} />
        <meshStandardMaterial color={bronze} metalness={0.78} roughness={0.27} />
      </mesh>
      <mesh position={[0, 0, 0.108]}>
        <circleGeometry args={[1.19, 72]} />
        <meshStandardMaterial color="#55222c" metalness={0.3} roughness={0.42} />
      </mesh>
      <mesh position={[0, 0, 0.125]}>
        <circleGeometry args={[1.145, 72]} />
        <meshBasicMaterial map={texture} toneMapped={false} />
      </mesh>
      <mesh position={[0, 0, 0.145]}>
        <torusGeometry args={[1.22, 0.045, 18, 72]} />
        <meshStandardMaterial color="#e3bf80" metalness={0.86} roughness={0.2} />
      </mesh>
    </group>
  )
}

function StaticSeal() {
  return (
    <div className="seal-fallback" aria-hidden="true">
      <img src={emblem} alt="" />
    </div>
  )
}

export function SealScene({ phase }: SealSceneProps) {
  const reduceMotion = useReducedMotion()
  const compact = useCompactViewport()

  if (reduceMotion || compact) return <StaticSeal />

  return (
    <div className="seal-scene" aria-label="Sello de Concilia" role="img">
      <div className="seal-canvas-fallback" aria-hidden="true"><img src={emblem} alt="" /></div>
      <Canvas dpr={[1, 1.5]} camera={{ position: [0, 0, 4.4], fov: 33 }} shadows gl={{ alpha: true }}>
        <ambientLight intensity={1.35} />
        <directionalLight position={[3, 3, 4]} intensity={2.15} color="#ffe4ad" castShadow />
        <directionalLight position={[-3, -1, 2]} intensity={0.85} color="#9d5361" />
        <Seal phase={phase} />
      </Canvas>
    </div>
  )
}
