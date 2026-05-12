export default function CommandSection({ eyebrow, title, description, actions = null, children, className = '' }) {
  return (
    <section className={`panel command-panel ${className}`.trim()}>
      <div className="panel-header">
        <div>
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h2>{title}</h2>
          {description ? <p className="muted">{description}</p> : null}
        </div>
        {actions}
      </div>
      {children}
    </section>
  )
}
