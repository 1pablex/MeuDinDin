/**
 * Máscara de valor em reais no estilo app de banco: o usuário digita só
 * números e eles entram pela direita (centavos). 123456 -> "1.234,56".
 * O valor "de verdade" trafega como string decimal com ponto ("1234.56").
 */
const MAX_DIGITS = 12 // até R$ 9.999.999.999,99

const fmt = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** Dígitos digitados -> string decimal para a API ("" quando vazio ou zero). */
export function digitsToDecimal(raw: string): string {
  const digits = raw.replace(/\D/g, '').replace(/^0+/, '').slice(0, MAX_DIGITS)
  if (!digits) return ''
  const cents = digits.padStart(3, '0')
  return `${cents.slice(0, -2)}.${cents.slice(-2)}`
}

/** String decimal ("1234.5", "1234.50", 1234.5) -> texto exibido ("1.234,50"). */
export function decimalToDisplay(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return ''
  const n = typeof value === 'number' ? value : Number.parseFloat(value)
  if (!Number.isFinite(n) || n === 0) return ''
  return fmt.format(n)
}

/** Converte um valor vindo da API ("120.50") para o formato do campo ("120.50"). */
export function normalizeDecimal(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return ''
  const n = typeof value === 'number' ? value : Number.parseFloat(value)
  return Number.isFinite(n) && n > 0 ? n.toFixed(2) : ''
}
