export default function CommandPageHeader({ eyebrow = 'Command Center', title, description, badges = [], actions = null }) {
  return (
    <header className="command-page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {description ? <p className="command-page-header__description">{description}</p> : null}
        {badges.length > 0 ? (
          <div className="button-row">
            {badges.map(badge => (
              <span key={badge} className="state-chip">{badge}</span>
            ))}
          </div>
        ) : null}
      </div>
      {actions ? <div className="command-page-header__actions">{actions}</div> : null}
    </header>
  )
}
