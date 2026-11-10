import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Em dev, /api é repassado ao Django: mesma origem, então o cookie httpOnly
// do refresh token funciona sem CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
})
