import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter, Routes, Route } from 'react-router-dom'
import './index.css'

import App from './App.tsx'
import SellerPage from './sellerpage.tsx'
import SellerDashboard from './SellerDashboard.tsx'

function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-stone-950 px-6 text-center text-white">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.3em] text-orange-500">
          Shopora
        </p>

        <h1 className="mt-5 text-6xl font-bold">404</h1>

        <p className="mt-4 text-stone-400">
          The page you are looking for could not be found.
        </p>

        <a
          href="#/"
          className="mt-8 inline-flex rounded-xl bg-orange-600 px-7 py-3 font-semibold text-white transition hover:bg-orange-700"
        >
          Return to Shopora
        </a>
      </div>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <HashRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/seller" element={<SellerPage />} />
        <Route path="/seller/dashboard" element={<SellerDashboard />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </HashRouter>
  </StrictMode>,
)
