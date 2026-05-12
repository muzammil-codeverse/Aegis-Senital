import { useEffect, useMemo } from 'react'
import { useCommandPalette } from '../../hooks/useCommandPalette'
import { useGlobalSearch } from '../../hooks/useGlobalSearch'
import { useRuntimeStatus } from '../../hooks/useRuntimeStatus'
import { getVisibleCommandNavigation } from '../../navigation/commandNavigation'
import { commandCenterCssVars } from '../../styles/commandCenterTheme'
import CommandPalette from '../command/CommandPalette'
import RuntimeStatusStrip from '../command/RuntimeStatusStrip'
import { useAuth } from '../../hooks/useAuth'
import CommandSidebar from './CommandSidebar'
import CommandStatusBar from './CommandStatusBar'
import CommandTopBar from './CommandTopBar'

export default function CommandCenterShell({
  children,
  currentPage,
  onNavigate,
  pageMeta,
  metrics,
  websocketStatus,
  lastMessageAt,
  reconnectCount,
}) {
  const auth = useAuth()
  const runtimeStatus = useRuntimeStatus()
  const navigation = useMemo(() => getVisibleCommandNavigation(auth.hasPermission), [auth.hasPermission])
  const palette = useCommandPalette()
  const liveSearch = useGlobalSearch({ enabled: palette.isOpen, query: palette.query })

  useEffect(() => {
    if (palette.selectedIndex < liveSearch.flatResults.length) return
    palette.setSelectedIndex(0)
  }, [liveSearch.flatResults.length, palette.selectedIndex, palette.setSelectedIndex])

  useEffect(() => {
    if (!palette.isOpen) return undefined

    function onKeyDown(event) {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        palette.setSelectedIndex(index => (
          liveSearch.flatResults.length > 0 ? (index + 1) % liveSearch.flatResults.length : 0
        ))
      } else if (event.key === 'ArrowUp') {
        event.preventDefault()
        palette.setSelectedIndex(index => (
          liveSearch.flatResults.length > 0 ? (index - 1 + liveSearch.flatResults.length) % liveSearch.flatResults.length : 0
        ))
      } else if (event.key === 'Enter' && liveSearch.flatResults.length > 0) {
        event.preventDefault()
        const result = liveSearch.flatResults[palette.selectedIndex]
        liveSearch.navigateForResult(result)
        palette.close()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [
    liveSearch.flatResults,
    liveSearch.navigateForResult,
    palette.close,
    palette.isOpen,
    palette.selectedIndex,
    palette.setSelectedIndex,
  ])

  return (
    <div className="command-center-shell" style={commandCenterCssVars()}>
      <CommandSidebar currentPage={currentPage} navigation={navigation} onNavigate={onNavigate} runtimeStatus={runtimeStatus} />
      <div className="command-center-shell__frame">
        <CommandTopBar
          pageMeta={pageMeta}
          websocketStatus={websocketStatus}
          lastMessageAt={lastMessageAt}
          reconnectCount={reconnectCount}
          runtimeStatus={runtimeStatus}
          onOpenPalette={palette.open}
        />
        <RuntimeStatusStrip runtimeStatus={runtimeStatus} compact />
        <main className="command-center-shell__main">{children}</main>
        <CommandStatusBar metrics={metrics} runtimeStatus={runtimeStatus} currentPage={currentPage} />
      </div>
      <CommandPalette
        isOpen={palette.isOpen}
        query={palette.query}
        sections={liveSearch.sections}
        flatResults={liveSearch.flatResults}
        selectedIndex={palette.selectedIndex}
        loading={liveSearch.loading}
        error={liveSearch.error}
        onClose={palette.close}
        onQueryChange={palette.setQuery}
        onSelectIndex={(index, confirm = false) => {
          palette.setSelectedIndex(index)
          if (confirm) {
            const result = liveSearch.flatResults[index]
            liveSearch.navigateForResult(result)
            palette.close()
          }
        }}
      />
    </div>
  )
}
