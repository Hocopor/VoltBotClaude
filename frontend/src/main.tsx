import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import App from './App'
import './index.css'

const qc = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 10_000, retry: 1 },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <App />
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: { background: '#111318', color: '#e6edf3', border: '1px solid #1e2230' },
          success: { iconTheme: { primary: '#00d395', secondary: '#111318' } },
          error:   { iconTheme: { primary: '#f6465d', secondary: '#111318' } },
        }}
      />
    </QueryClientProvider>
  </React.StrictMode>
)
