import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8502',
        changeOrigin: true,
      },
      // patient-service (MPI): demographics, alerts, identifiers
      '/mpi': {
        target: 'http://localhost:8501',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/mpi/, ''),
      },
      // appointment-service (scheduling)
      '/sched': {
        target: 'http://localhost:8503',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/sched/, ''),
      },
      // queue-service (digital queues)
      '/q': {
        target: 'http://localhost:8504',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/q/, ''),
      },
      // billing-service (finance)
      '/bill': {
        target: 'http://localhost:8509',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/bill/, ''),
      },
      // prescription-service (prescribing)
      '/rx': {
        target: 'http://localhost:8510',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/rx/, ''),
      },
      // pharmacy-service (dispensing)
      '/pharm': {
        target: 'http://localhost:8511',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/pharm/, ''),
      },
      // laboratory-service
      '/lab': {
        target: 'http://localhost:8512',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/lab/, ''),
      },
      // radiology-service
      '/rad': {
        target: 'http://localhost:8513',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/rad/, ''),
      },
      // inventory-service
      '/inv': {
        target: 'http://localhost:8514',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/inv/, ''),
      },
      // workflow-service
      '/wf': {
        target: 'http://localhost:8515',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/wf/, ''),
      },
      // clinical-documentation-service
      '/doc': {
        target: 'http://localhost:8516',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/doc/, ''),
      },
      // insurance-service
      '/ins': {
        target: 'http://localhost:8517',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/ins/, ''),
      },
      // reporting-service
      '/rpt': {
        target: 'http://localhost:8518',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/rpt/, ''),
      },
    },
  },
})