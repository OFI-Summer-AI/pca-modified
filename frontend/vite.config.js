import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/analyze': 'http://localhost:8001',
      '/analyze-default': 'http://localhost:8001',
      '/default-files': 'http://localhost:8001',
      '/rca': { target: 'http://localhost:8001', timeout: 900000 },
      '/summary': 'http://localhost:8001',
      '/chat': 'http://localhost:8001',
      '/orders': 'http://localhost:8001',
      '/send-alerts': 'http://localhost:8001',
      '/health': 'http://localhost:8001',
    },
  },
});
