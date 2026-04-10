import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@/components': path.resolve(__dirname, './src/components'),
      '@/services': path.resolve(__dirname, './src/services'),
      '@/analytics': path.resolve(__dirname, './src/services/analytics')
    }
  },
  define: {
    // Only expose specific environment variables to prevent leaking sensitive server-side variables
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV)
  },
  build: {
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          // Separate PostHog into its own chunk for lazy loading
          'posthog': ['posthog-js']
        }
      }
    }
  },
  server: {
    port: 3000,
    open: true
  }
});