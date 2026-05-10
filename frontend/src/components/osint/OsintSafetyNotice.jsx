export default function OsintSafetyNotice() {
  return (
    <article className="case-subcard">
      <div className="panel-subheader">
        <h3>Analyst-provided enrichment</h3>
        <span>Requires operator review</span>
      </div>
      <p className="drawer-description">
        Manual source material only. Not independently verified. No automatic web scraping, social-media lookup,
        face-to-web search, or identity attribution is performed in this workflow.
      </p>
      <div className="button-row">
        <span className="state-chip">Manual source</span>
        <span className="state-chip">Not independently verified</span>
      </div>
    </article>
  )
}
