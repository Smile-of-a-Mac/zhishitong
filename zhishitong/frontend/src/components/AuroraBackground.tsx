import React, { useEffect, useRef } from 'react'

interface HSLColor { h: number; s: number; l: number }
interface ColorPair { c1: HSLColor; c2: HSLColor }
interface GlowOrb { x: number; y: number; r: number; color: string; phase: number; drift: number }

class AuroraLine {
  i: number
  nodes: { x: number; baseY: number; lx: number; ly: number }[] = []
  colorPair!: ColorPair
  seed!: number

  constructor(i: number) {
    this.i = i
    this.refresh()
    for (let n = 0; n <= 6; n++) {
      this.nodes.push({ x: 0, baseY: 0, lx: 0, ly: 0 })
    }
  }

  refresh() {
    const p = getPalette()
    this.colorPair = p[this.i % p.length]
    // 首次构造时生成随机种子，后续 refresh（暗色模式切换）保留形状
    if (this.seed === undefined) this.seed = Math.random() * 100
  }

  update(ctx: CanvasRenderingContext2D, w: number, h: number, tick: number) {
    ctx.beginPath()
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    const alpha = isDark ? 0.2 : 0.16
    const xOff = Math.sin(tick * 0.0032 + this.i) * 76

    ctx.moveTo(-200, h)
    for (let n = 0; n <= 6; n++) {
      const node = this.nodes[n]
      node.x = (w / 6) * n
      node.baseY = h * (0.38 + this.i * 0.08)
      const noise =
        Math.sin(tick * 0.011 + n * 0.8 + this.seed) * 78 +
        Math.cos(tick * 0.019 + n) * 28
      const tx = node.x + xOff
      const ty = node.baseY + noise
      if (n === 0) {
        ctx.lineTo(tx, ty)
      } else {
        const prev = this.nodes[n - 1]
        const cx = (prev.lx + tx) / 2
        const cy = (prev.ly + ty) / 2
        ctx.quadraticCurveTo(prev.lx, prev.ly, cx, cy)
      }
      node.ly = ty
      node.lx = tx
    }
    ctx.lineTo(w + 200, h)

    const g = ctx.createLinearGradient(0, h, 0, 0)
    g.addColorStop(0, 'transparent')
    g.addColorStop(
      0.2,
      `hsla(${this.colorPair.c1.h},${this.colorPair.c1.s}%,${this.colorPair.c1.l}%,${alpha})`
    )
    g.addColorStop(
      0.8,
      `hsla(${this.colorPair.c2.h},${this.colorPair.c2.s}%,${this.colorPair.c2.l}%,${alpha})`
    )
    g.addColorStop(1, 'transparent')
    ctx.fillStyle = g
    ctx.fill()
  }
}

function getPalette(): ColorPair[] {
  const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  return isDark
    ? [
        { c1: { h: 214, s: 86, l: 42 }, c2: { h: 194, s: 76, l: 46 } },
        { c1: { h: 206, s: 72, l: 38 }, c2: { h: 250, s: 58, l: 48 } },
        { c1: { h: 178, s: 62, l: 34 }, c2: { h: 214, s: 62, l: 42 } },
      ]
    : [
        { c1: { h: 210, s: 72, l: 72 }, c2: { h: 195, s: 58, l: 76 } },
        { c1: { h: 205, s: 52, l: 70 }, c2: { h: 245, s: 42, l: 76 } },
        { c1: { h: 175, s: 46, l: 70 }, c2: { h: 212, s: 48, l: 74 } },
      ]
}

function drawGeminiGlow(ctx: CanvasRenderingContext2D, w: number, h: number, tick: number) {
  const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  const alpha = isDark ? 0.2 : 0.16
  const minSide = Math.min(w, h)
  const orbs: GlowOrb[] = [
    { x: 0.18, y: 0.2, r: 0.42, color: '66, 133, 244', phase: 0.1, drift: 0.009 },
    { x: 0.78, y: 0.18, r: 0.34, color: '52, 168, 83', phase: 1.7, drift: 0.007 },
    { x: 0.36, y: 0.82, r: 0.46, color: '155, 81, 224', phase: 3.2, drift: 0.008 },
    { x: 0.88, y: 0.76, r: 0.32, color: '251, 188, 5', phase: 4.4, drift: 0.006 },
  ]

  ctx.save()
  ctx.globalCompositeOperation = isDark ? 'screen' : 'multiply'

  for (const orb of orbs) {
    const breath = 0.9 + Math.sin(tick * 0.024 + orb.phase) * 0.1
    const px = w * orb.x + Math.sin(tick * orb.drift + orb.phase) * minSide * 0.07
    const py = h * orb.y + Math.cos(tick * orb.drift * 0.85 + orb.phase) * minSide * 0.055
    const radius = minSide * orb.r * breath
    const g = ctx.createRadialGradient(px, py, 0, px, py, radius)

    g.addColorStop(0, `rgba(${orb.color}, ${alpha})`)
    g.addColorStop(0.36, `rgba(${orb.color}, ${alpha * 0.42})`)
    g.addColorStop(0.72, `rgba(${orb.color}, ${alpha * 0.12})`)
    g.addColorStop(1, 'rgba(255, 255, 255, 0)')
    ctx.fillStyle = g
    ctx.beginPath()
    ctx.arc(px, py, radius, 0, Math.PI * 2)
    ctx.fill()
  }

  const cx = w * 0.5 + Math.sin(tick * 0.005) * minSide * 0.04
  const cy = h * 0.48 + Math.cos(tick * 0.006) * minSide * 0.035
  const halo = ctx.createRadialGradient(cx, cy, 0, cx, cy, minSide * 0.58)
  halo.addColorStop(0, isDark ? 'rgba(160, 190, 255, 0.08)' : 'rgba(255, 255, 255, 0.36)')
  halo.addColorStop(0.54, isDark ? 'rgba(120, 160, 255, 0.03)' : 'rgba(255, 255, 255, 0.18)')
  halo.addColorStop(1, 'rgba(255, 255, 255, 0)')
  ctx.fillStyle = halo
  ctx.beginPath()
  ctx.arc(cx, cy, minSide * 0.58, 0, Math.PI * 2)
  ctx.fill()

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
    const dpr = window.devicePixelRatio || 1
    const lines: AuroraLine[] = [new AuroraLine(0), new AuroraLine(1), new AuroraLine(2)]
    let animationId: number
    let tick = 0

    function resize() {
      w = window.innerWidth
      h = window.innerHeight
      canvas!.width = w * dpr
      canvas!.height = h * dpr
      ctx!.setTransform(1, 0, 0, 1, 0, 0)
      ctx!.scale(dpr, dpr)
    }

    function loop() {
      ctx!.clearRect(0, 0, w, h)
      ctx!.globalCompositeOperation = window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'screen'
        : 'source-over'
      tick += 0.46
      drawGeminiGlow(ctx!, w, h, tick)
      for (const line of lines) {
        line.update(ctx!, w, h, tick)
      }
      animationId = requestAnimationFrame(loop)
    }

    resize()
    loop()

    const onResize = () => resize()
    window.addEventListener('resize', onResize)

    const darkMode = window.matchMedia('(prefers-color-scheme: dark)')
    const onColorSchemeChange = () => {
      for (const line of lines) line.refresh()
    }
    darkMode.addEventListener('change', onColorSchemeChange)

    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', onResize)
      darkMode.removeEventListener('change', onColorSchemeChange)
    }
  }, [])

  return <canvas id="aurora-canvas" ref={canvasRef} />
}
