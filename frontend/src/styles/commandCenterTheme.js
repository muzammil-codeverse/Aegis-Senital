export const commandCenterTheme = {
  fonts: {
    display: '"Space Grotesk", "Segoe UI", sans-serif',
    body: '"IBM Plex Sans", "Segoe UI", sans-serif',
    mono: '"IBM Plex Mono", "Consolas", monospace',
  },
  colors: {
    background: '#061018',
    backgroundElevated: '#0b1721',
    panel: 'rgba(11, 23, 33, 0.86)',
    panelStrong: 'rgba(15, 29, 42, 0.96)',
    panelSoft: 'rgba(18, 33, 48, 0.78)',
    border: 'rgba(93, 122, 152, 0.26)',
    borderStrong: 'rgba(120, 156, 191, 0.46)',
    text: '#dce6f2',
    textStrong: '#f7fbff',
    muted: '#8da0b5',
    accent: '#5bc0eb',
    accentWarm: '#f2c14e',
    success: '#4ade80',
    warning: '#fbbf24',
    danger: '#fb7185',
    info: '#60a5fa',
  },
}

export function commandCenterCssVars() {
  return {
    '--cc-font-display': commandCenterTheme.fonts.display,
    '--cc-font-body': commandCenterTheme.fonts.body,
    '--cc-font-mono': commandCenterTheme.fonts.mono,
    '--cc-bg': commandCenterTheme.colors.background,
    '--cc-bg-elevated': commandCenterTheme.colors.backgroundElevated,
    '--cc-panel': commandCenterTheme.colors.panel,
    '--cc-panel-strong': commandCenterTheme.colors.panelStrong,
    '--cc-panel-soft': commandCenterTheme.colors.panelSoft,
    '--cc-border': commandCenterTheme.colors.border,
    '--cc-border-strong': commandCenterTheme.colors.borderStrong,
    '--cc-text': commandCenterTheme.colors.text,
    '--cc-text-strong': commandCenterTheme.colors.textStrong,
    '--cc-muted': commandCenterTheme.colors.muted,
    '--cc-accent': commandCenterTheme.colors.accent,
    '--cc-accent-warm': commandCenterTheme.colors.accentWarm,
    '--cc-success': commandCenterTheme.colors.success,
    '--cc-warning': commandCenterTheme.colors.warning,
    '--cc-danger': commandCenterTheme.colors.danger,
    '--cc-info': commandCenterTheme.colors.info,
  }
}

export function normalizeRuntimeTone(status) {
  const value = String(status || 'unknown').toLowerCase()
  if (['ok', 'ready', 'healthy', 'normal', 'open', 'connected', 'active', 'running'].includes(value)) {
    return 'ok'
  }
  if (['warning', 'warn', 'degraded', 'partial', 'idle', 'paused', 'starting', 'reconnecting'].includes(value)) {
    return 'degraded'
  }
  if (['critical', 'error', 'failed', 'offline', 'closed', 'auth_error', 'unavailable'].includes(value)) {
    return 'critical'
  }
  return 'unknown'
}
