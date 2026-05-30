import React, { useEffect, useRef } from 'react'
import { addAiActivityListener } from '../utils/aiActivity'

interface BlobNode {
  x: number
  y: number
  size: number
  color: string
  phase: number
  driftX: number
  driftY: number
  focusX: number
  focusY: number
}

const BLOBS: BlobNode[] = [
  { x: 0.16, y: 0.12, size: 0.52, color: '77, 139, 255', phase: 0.2, driftX: 0.0031, driftY: 0.0022, focusX: 0.42, focusY: 0.3 },
  { x: 0.84, y: 0.14, size: 0.42, color: '84, 212, 190', phase: 1.4, driftX: 0.0024, driftY: 0.0034, focusX: 0.56, focusY: 0.32 },
  { x: 0.72, y: 0.78, size: 0.54, color: '143, 108, 255', phase: 2.6, driftX: 0.0035, driftY: 0.0026, focusX: 0.58, focusY: 0.48 },
  { x: 0.22, y: 0.78, size: 0.46, color: '115, 197, 255', phase: 3.8, driftX: 0.0028, driftY: 0.003, focusX: 0.44, focusY: 0.48 },
  { x: 0.52, y: 0.04, size: 0.38, color: '235, 241, 255', phase: 5.1, driftX: 0.002, driftY: 0.0027, focusX: 0.5, focusY: 0.24 },
  { x: 0.5, y: 0.9, size: 0.5, color: '182, 155, 255', phase: 6.0, driftX: 0.0023, driftY: 0.0021, focusX: 0.5, focusY: 0.56 },
]

function mix(a: number, b: number, t: number) {
  return a + (b - a) * t
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
      Math.sin(a * 5 + tick * 0.003 + phase * 0.4) * 0.012
    const r = radius * (1 + organic * (0.7 + energy * 1.1))
    const px = x + Math.cos(a) * r
    const py = y + Math.sin(a) * r
    if (i === 0) ctx.moveTo(px, py)
    else ctx.lineTo(px, py)
  }
  ctx.closePath()
  ctx.fill()
}

function drawMicroTexture(ctx: CanvasRenderingContext2D, w: number, h: number, tick: number, energy: number) {
  const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  const alpha = (isDark ? 0.018 : 0.026) + energy * (isDark ? 0.045 : 0.038)
  const gap = 72
  const offsetX = Math.sin(tick * (0.002 + energy * 0.004)) * (18 + energy * 34)
  const offsetY = Math.cos(tick * (0.0017 + energy * 0.003)) * (16 + energy * 28)

  ctx.save()
  ctx.globalCompositeOperation = isDark ? 'screen' : 'source-over'
  ctx.lineWidth = 1
  ctx.strokeStyle = `rgba(90, 140, 210, ${alpha})`

  for (let y = -gap; y < h + gap; y += gap) {
    ctx.beginPath()
    for (let x = -gap; x < w + gap; x += 16) {
      const px = x + offsetX
      const py = y + offsetY + Math.sin(x * 0.012 + tick * (0.004 + energy * 0.012)) * (4 + energy * 16)
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
) {
  const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  const minSide = Math.min(w, h)
  const speed = 1 + energy * 3.4

  ctx.save()
  ctx.globalCompositeOperation = isDark ? 'screen' : 'multiply'

  for (const blob of BLOBS) {
    const naturalX =
      blob.x +
      Math.sin(tick * blob.driftX * speed + blob.phase) * (0.055 + energy * 0.04) +
      Math.sin(tick * blob.driftY * (0.72 + energy * 1.1) + blob.phase * 1.7) * (0.024 + energy * 0.026)
    const naturalY =
      blob.y +
      Math.cos(tick * blob.driftY * speed + blob.phase) * (0.05 + energy * 0.04) +
      Math.sin(tick * blob.driftX * (0.86 + energy * 1.15) + blob.phase * 0.9) * (0.02 + energy * 0.024)

    const focusStrength = energy * 0.76
    const x = mix(naturalX, blob.focusX, focusStrength) * w
    const y = mix(naturalY, blob.focusY, focusStrength) * h
    const breathe = 0.94 + Math.sin(tick * (0.006 + energy * 0.018) + blob.phase) * (0.055 + energy * 0.07)
    const radius = minSide * blob.size * breathe * (1 - energy * 0.1)
    const alpha = (isDark ? 0.14 : 0.11) + energy * (isDark ? 0.22 : 0.18)

    drawBlob(ctx, x, y, radius, blob.color, alpha, tick, blob.phase, energy)
  }

  const focusX = w * (0.5 + Math.sin(tick * 0.0017) * 0.025)
  const focusY = h * (0.38 + Math.cos(tick * 0.0021) * 0.018)
  const focusAlpha = (isDark ? 0.08 : 0.16) + energy * 0.28
  drawBlob(ctx, focusX, focusY, minSide * (0.46 - energy * 0.08), '245, 249, 255', focusAlpha, tick, 4.8, energy)

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
      energy += (targetEnergy - energy) * 0.085
      tick += 0.58 + energy * 1.55
      canvas!.dataset.aiActive = energy > 0.06 ? 'true' : 'false'

      drawMicroTexture(ctx!, w, h, tick, energy)
      drawFluidField(ctx!, w, h, tick, energy)

      animationId = requestAnimationFrame(loop)
    }

    resize()
    loop()

    const onResize = () => resize()
    window.addEventListener('resize', onResize)

    const removeAiActivityListener = addAiActivityListener(active => {
      targetEnergy = active ? 1 : 0
    })

    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', onResize)
      removeAiActivityListener()
    }
  }, [])

  return <canvas id="aurora-canvas" ref={canvasRef} />
}
