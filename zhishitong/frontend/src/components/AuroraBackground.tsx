import React, { useEffect, useRef } from 'react'

interface HSLColor { h: number; s: number; l: number }
interface ColorPair { c1: HSLColor; c2: HSLColor }

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
    const alpha = isDark ? 0.6 : 0.5
    const xOff = Math.sin(tick * 0.002 + this.i) * 100

    ctx.moveTo(-200, h)
    for (let n = 0; n <= 6; n++) {
      const node = this.nodes[n]
      node.x = (w / 6) * n
      node.baseY = h * (0.3 + this.i * 0.1)
      const noise =
        Math.sin(tick * 0.008 + n * 0.8 + this.seed) * 150 +
        Math.cos(tick * 0.015 + n) * 50
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
        { c1: { h: 220, s: 100, l: 45 }, c2: { h: 280, s: 90, l: 45 } },
        { c1: { h: 160, s: 100, l: 40 }, c2: { h: 200, s: 90, l: 45 } },
        { c1: { h: 300, s: 90, l: 45 }, c2: { h: 340, s: 100, l: 50 } },
      ]
    : [
        { c1: { h: 210, s: 85, l: 65 }, c2: { h: 260, s: 80, l: 70 } },
        { c1: { h: 170, s: 80, l: 60 }, c2: { h: 200, s: 85, l: 65 } },
        { c1: { h: 280, s: 80, l: 70 }, c2: { h: 320, s: 85, l: 75 } },
      ]
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
      ctx!.scale(dpr, dpr)
    }

    function loop() {
      ctx!.clearRect(0, 0, w, h)
      ctx!.globalCompositeOperation = window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'screen'
        : 'source-over'
      tick += 0.35  // ≈1/3 速度，极光流动更舒缓
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
