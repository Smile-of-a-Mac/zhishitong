import React, { useEffect, useRef } from 'react'
import { addAiActivityListener } from '../utils/aiActivity'

interface BlobNode {
  x: number
  y: number
  size: number
  colors: [string, string]
  phase: number
  driftX: number
  driftY: number
  focusX: number
  focusY: number
}

const BLOBS: BlobNode[] = [
  { x: 0.16, y: 0.12, size: 0.52, colors: ['60, 130, 255', '40, 220, 180'], phase: 0.2, driftX: 0.0031, driftY: 0.0022, focusX: 0.42, focusY: 0.3 },
  { x: 0.84, y: 0.14, size: 0.42, colors: ['40, 220, 180', '150, 80, 255'], phase: 1.4, driftX: 0.0024, driftY: 0.0034, focusX: 0.56, focusY: 0.32 },
  { x: 0.72, y: 0.78, size: 0.54, colors: ['150, 80, 255', '200, 140, 255'], phase: 2.6, driftX: 0.0035, driftY: 0.0026, focusX: 0.58, focusY: 0.48 },
  { x: 0.22, y: 0.78, size: 0.46, colors: ['200, 140, 255', '255, 120, 180'], phase: 3.8, driftX: 0.0028, driftY: 0.003, focusX: 0.44, focusY: 0.48 },
  { x: 0.52, y: 0.04, size: 0.38, colors: ['255, 200, 100', '255, 255, 255'], phase: 5.1, driftX: 0.002, driftY: 0.0027, focusX: 0.5, focusY: 0.24 },
  { x: 0.5, y: 0.9, size: 0.5, colors: ['200, 140, 255', '60, 130, 255'], phase: 6.0, driftX: 0.0023, driftY: 0.0021, focusX: 0.5, focusY: 0.56 },
]

function mix(a: number, b: number, t: number) {
  return a + (b - a) * t
}

function smoothstep(t: number) {
  const x = Math.max(0, Math.min(1, t))
  return x * x * (3 - 2 * x)
}

function parseRgb(color: string) {
  return color.split(',').map(v => Number(v.trim())) as [number, number, number]
}

function mixColor(a: string, b: string, t: number) {
  const ca = parseRgb(a)
  const cb = parseRgb(b)
  return ca.map((value, i) => Math.round(mix(value, cb[i], t))).join(', ')
}

function drawBlob(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  color: string,
  alpha: number,
  tick: number,
  phase: number,
  energy: number,
  flow: number,
) {
  const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius)
  gradient.addColorStop(0, `rgba(${color}, ${alpha})`)
  gradient.addColorStop(0.38, `rgba(${color}, ${alpha * 0.45})`)
  gradient.addColorStop(0.74, `rgba(${color}, ${alpha * 0.14})`)
  gradient.addColorStop(1, 'rgba(255, 255, 255, 0)')
  ctx.fillStyle = gradient
  ctx.beginPath()
  const points = 18
  for (let i = 0; i <= points; i++) {
    const a = (i / points) * Math.PI * 2
    const organic =
      Math.sin(a * 2 + tick * 0.006 + phase) * 0.025 +
      Math.cos(a * 3 - tick * 0.004 + phase * 1.7) * 0.018 +
      Math.sin(a * 5 + tick * 0.003 + phase * 0.4 + flow * 0.35) * 0.012
    const r = radius * (1 + organic * (0.7 + energy * 1.45))
    const px = x + Math.cos(a) * r
    const py = y + Math.sin(a) * r
    if (i === 0) ctx.moveTo(px, py)
    else ctx.lineTo(px, py)
  }
  ctx.closePath()
  ctx.fill()
}

function drawMicroTexture(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  tick: number,
  energy: number,
  motionEnergy: number,
) {
  const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  const alpha = (isDark ? 0.03 : 0.04) + energy * (isDark ? 0.052 : 0.046)
  const gap = 72
  const offsetX = Math.sin(tick * (0.002 + motionEnergy * 0.0024)) * (18 + energy * 30)
  const offsetY = Math.cos(tick * (0.0017 + motionEnergy * 0.002)) * (16 + energy * 26)

  ctx.save()
  ctx.globalCompositeOperation = isDark ? 'screen' : 'source-over'
  ctx.lineWidth = 1
  ctx.strokeStyle = `rgba(90, 140, 210, ${alpha})`

  for (let y = -gap; y < h + gap; y += gap) {
    ctx.beginPath()
    for (let x = -gap; x < w + gap; x += 16) {
      const px = x + offsetX
      const py = y + offsetY + Math.sin(x * 0.012 + tick * (0.004 + motionEnergy * 0.006)) * (4 + energy * 14)
      if (x === -gap) ctx.moveTo(px, py)
      else ctx.lineTo(px, py)
    }
    ctx.stroke()
  }
  ctx.restore()
}

function drawFluidField(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  tick: number,
  energy: number,
  visualEnergy: number,
  flow: number,
) {
  const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  const minSide = Math.min(w, h)
  const speed = 1 + energy * 1.35

  ctx.save()
  ctx.globalCompositeOperation = isDark ? 'screen' : 'multiply'

  for (const blob of BLOBS) {
    const naturalX =
      blob.x +
      Math.sin(tick * blob.driftX * speed + blob.phase + flow * 0.08) * (0.055 + visualEnergy * 0.04) +
      Math.sin(tick * blob.driftY * (0.72 + energy * 0.35) + blob.phase * 1.7) * (0.024 + visualEnergy * 0.024)
    const naturalY =
      blob.y +
      Math.cos(tick * blob.driftY * speed + blob.phase + flow * 0.07) * (0.05 + visualEnergy * 0.036) +
      Math.sin(tick * blob.driftX * (0.86 + energy * 0.38) + blob.phase * 0.9) * (0.02 + visualEnergy * 0.022)

    const focusStrength = visualEnergy * 0.46
    const x = mix(naturalX, blob.focusX, focusStrength) * w
    const y = mix(naturalY, blob.focusY, focusStrength) * h
    const breathe = 0.94 + Math.sin(tick * (0.006 + energy * 0.004) + blob.phase + flow * 0.11) * (0.055 + visualEnergy * 0.055)
    const radius = minSide * blob.size * breathe * (1 - visualEnergy * 0.06)
    const alpha = (isDark ? 0.22 : 0.16) + visualEnergy * (isDark ? 0.23 : 0.18)
    const colorShift = (Math.sin(flow * 0.42 + blob.phase) + 1) / 2
    const color = mixColor(blob.colors[0], blob.colors[1], colorShift * visualEnergy)

    drawBlob(ctx, x, y, radius, color, alpha, tick, blob.phase, visualEnergy, flow)
  }

  const focusX = w * (0.5 + Math.sin(tick * 0.0017) * 0.025)
  const focusY = h * (0.38 + Math.cos(tick * 0.0021) * 0.018)
  const focusAlpha = (isDark ? 0.15 : 0.25) + visualEnergy * 0.26
  const focusColor = mixColor('255, 255, 255', '120, 190, 255', visualEnergy * ((Math.sin(flow * 0.36) + 1) / 2) * 0.55)
  drawBlob(ctx, focusX, focusY, minSide * (0.46 - visualEnergy * 0.045), focusColor, focusAlpha, tick, 4.8, visualEnergy, flow)

  ctx.restore()
}

export default function AuroraBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let w = window.innerWidth
    let h = window.innerHeight
    let dpr = window.devicePixelRatio || 1
    let animationId: number
    let tick = 0
    let targetEnergy = 0
    let energy = 0
    let visualEnergy = 0
    let motionEnergy = 0
    let flow = 0
    let activeSince = 0
    let requestedActive = false
    let activeState = false
    let deactivateAfter = 0

    function resize() {
      w = window.innerWidth
      h = window.innerHeight
      dpr = window.devicePixelRatio || 1
      canvas!.width = w * dpr
      canvas!.height = h * dpr
      ctx!.setTransform(1, 0, 0, 1, 0, 0)
      ctx!.scale(dpr, dpr)
    }

    function loop() {
      ctx!.clearRect(0, 0, w, h)
      const now = performance.now()
      if (requestedActive) {
        if (!activeState) {
          activeSince = now
          activeState = true
        }
        targetEnergy = 0.84
      } else if (activeState && now < deactivateAfter) {
        targetEnergy = 0.84
      } else if (now >= deactivateAfter) {
        activeState = false
        targetEnergy = 0
      }

      const ramp = targetEnergy > 0 ? smoothstep((performance.now() - activeSince) / 1400) : 1
      const easedTarget = targetEnergy * ramp
      const easing = easedTarget > energy ? 0.032 : 0.03
      energy += (easedTarget - energy) * easing
      visualEnergy += (energy - visualEnergy) * 0.026
      // Motion uses a slower low-pass energy so request-state jitter cannot jerk velocity.
      motionEnergy += (energy - motionEnergy) * (energy > motionEnergy ? 0.008 : 0.004)
      tick += 0.5 + motionEnergy * 0.55
      flow += 0.008 + motionEnergy * 0.014
      canvas!.dataset.aiActive = visualEnergy > 0.16 ? 'true' : 'false'

      drawMicroTexture(ctx!, w, h, tick, visualEnergy, motionEnergy)
      drawFluidField(ctx!, w, h, tick, motionEnergy, visualEnergy, flow)

      animationId = requestAnimationFrame(loop)
    }

    resize()
    loop()

    const onResize = () => resize()
    window.addEventListener('resize', onResize)

    const removeAiActivityListener = addAiActivityListener(active => {
      const now = performance.now()
      if (active) {
        requestedActive = true
        deactivateAfter = 0
      } else {
        requestedActive = false
        deactivateAfter = now + 900
      }
    })

    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', onResize)
      removeAiActivityListener()
    }
  }, [])

  return <canvas id="aurora-canvas" ref={canvasRef} />
}
