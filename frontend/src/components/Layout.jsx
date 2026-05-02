export default function Layout({ children }) {
  return (
    <div className="min-h-screen bg-slate-900 flex flex-col">
      <nav className="bg-slate-800 border-b border-slate-700 px-6 py-3 flex items-center gap-4">
        <span className="text-blue-400 font-bold text-lg">🛡 Sentinel AI</span>
        <a href="/" className="text-slate-400 hover:text-slate-100 text-sm transition-colors">Dashboard</a>
      </nav>
      <main className="flex-1">{children}</main>
      <footer className="text-center text-slate-600 text-xs py-3 border-t border-slate-800">
        Sentinel AI System — Phase 1
      </footer>
    </div>
  )
}
