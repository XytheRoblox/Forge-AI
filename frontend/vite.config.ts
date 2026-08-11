import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The API is same-origin and proxied, rather than an absolute
    // http://localhost:8000 the frontend calls directly. That's what lets one
    // tunnel serve the whole app: a remote browser given an absolute localhost
    // URL would try to reach its OWN machine's backend and fail.
    proxy: {
      // xfwd so the backend can tell a proxied request from a genuinely
      // local one. Without it, tunnelled traffic arrives here and reaches the
      // backend from 127.0.0.1, indistinguishable from someone at the keyboard.
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true, xfwd: true },
    },
    // ngrok serves the app on a hostname Vite has never heard of, and Vite
    // rejects unknown Host headers by default as DNS-rebinding protection.
    // The backend's own token check is what actually guards the API.
    allowedHosts: [".ngrok-free.dev", ".ngrok-free.app", ".ngrok.app", ".ngrok.io"],
  },
})
