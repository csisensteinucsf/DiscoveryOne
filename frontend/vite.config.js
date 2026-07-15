import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  return {
    plugins: [react()],
    define: {
      __APP_NAME__: JSON.stringify(env.VITE_APP_NAME || 'DiscoveryOne')
    },
    build: {
      outDir: 'dist',
      rollupOptions: {
        onwarn(warning, warn) {
          if (warning.code === 'CIRCULAR_DEPENDENCY') {
            throw new Error(`Circular frontend dependency: ${warning.message}`)
          }
          warn(warning)
        },
        output: {
          manualChunks: {
            react: ['react', 'react-dom'],
            router: ['react-router-dom']
          }
        }
      }
    }
  }
})
