import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In development the page talks to lab/demo.py (port 8080) through this proxy.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8080' } },
});
