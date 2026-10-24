import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: parseInt(process.env.VITE_PORT || '3010', 10),
    strictPort: true,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${process.env.VITE_BACKEND_PORT || '4010'}`,
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
