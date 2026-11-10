import { useEffect, useState } from 'react'

/** Segundos restantes até `until` (timestamp em ms), atualizado a cada segundo. */
export function useCountdown(until: number | null): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!until) return
    const tick = () => setNow(Date.now())
    const first = window.setTimeout(tick, 0) // sincroniza o relógio logo que o prazo muda
    const id = window.setInterval(() => {
      tick()
      if (Date.now() >= until) window.clearInterval(id)
    }, 1000)
    return () => {
      window.clearTimeout(first)
      window.clearInterval(id)
    }
  }, [until])

  return until ? Math.max(0, Math.ceil((until - now) / 1000)) : 0
}

export function mmss(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
