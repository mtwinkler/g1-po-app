import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { // <-- Add this server block
    proxy: { // <-- Add proxy configuration
      '/api': { // <-- When the frontend requests URLs starting with /api
        target: 'http://127.0.0.1:8080', // <-- Proxy them to your Flask backend URL
        changeOrigin: true, // <-- Needed for correct routing
        // rewrite: (path) => path.replace(/^\/api/, '') // <-- Uncomment if your Flask routes don't start with /api
      }
    }
  } // <-- End server block
})