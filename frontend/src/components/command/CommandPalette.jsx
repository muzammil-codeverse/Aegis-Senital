import { Search, Slash } from 'lucide-react'

export default function CommandPalette({
  isOpen,
  query,
  sections,
  flatResults,
  selectedIndex,
  loading,
  error,
  onClose,
  onQueryChange,
  onSelectIndex,
}) {
  if (!isOpen) return null

  return (
    <div className="command-palette-backdrop" role="presentation" onClick={onClose}>
      <div className="command-palette" role="dialog" aria-modal="true" aria-label="Command palette" onClick={event => event.stopPropagation()}>
        <div className="command-palette__search">
          <Search size={16} />
          <input
            aria-label="Search command palette"
            autoFocus
            value={query}
            onChange={event => onQueryChange(event.target.value)}
            placeholder="Search routes, cases, cameras, alerts, missions, fusion, governance, or identity candidates"
          />
          <span className="command-palette__hint">
            <Slash size={12} />
            Ctrl+K
          </span>
        </div>
        {loading ? <p className="command-palette__status">Searching operational data...</p> : null}
        {error ? <p className="command-palette__status error">{error}</p> : null}
        {!loading && flatResults.length === 0 ? (
          <p className="command-palette__status">No authorized results matched this query.</p>
        ) : null}
        <div className="command-palette__results">
          {sections.map(section => (
            <div key={section.title} className="command-palette__section">
              <p className="command-palette__section-title">{section.title}</p>
              <div className="command-palette__list">
                {section.items.map(item => {
                  const itemIndex = flatResults.findIndex(result => result.key === item.key)
                  return (
                    <button
                      key={item.key}
                      type="button"
                      className={`command-palette__item ${selectedIndex === itemIndex ? 'active' : ''}`}
                      onMouseEnter={() => onSelectIndex(itemIndex)}
                      onClick={() => onSelectIndex(itemIndex, true)}
                    >
                      <div>
                        <strong>{item.label}</strong>
                        <p>{item.description}</p>
                      </div>
                      <span>{item.meta}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
