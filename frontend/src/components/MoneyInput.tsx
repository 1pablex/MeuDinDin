import type { InputHTMLAttributes } from 'react'
import { decimalToDisplay, digitsToDecimal } from '../lib/money'

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type'> & {
  /** Valor decimal com ponto, ex. "1234.56" ("" = vazio) */
  value: string
  onChange: (decimal: string) => void
}

/** Campo de dinheiro com máscara pt-BR: digita 123456, aparece 1.234,56. */
export function MoneyInput({ value, onChange, className = '', ...rest }: Props) {
  return (
    <span className={`money-input ${className}`}>
      <span className="money-prefix" aria-hidden="true">
        R$
      </span>
      <input
        {...rest}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        value={decimalToDisplay(value)}
        placeholder={rest.placeholder ?? '0,00'}
        onChange={(e) => onChange(digitsToDecimal(e.target.value))}
      />
    </span>
  )
}
