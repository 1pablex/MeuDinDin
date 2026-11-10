import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Erro na interface', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="fatal" role="alert">
          <h1>Algo deu errado</h1>
          <p>Recarregue a página. Se o problema continuar, entre de novo.</p>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>
            Recarregar
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
