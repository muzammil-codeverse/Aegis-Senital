import { useCallback, useEffect, useState } from 'react'

export function useCommandPalette() {
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)

  const open = useCallback(() => {
    setIsOpen(true)
    setSelectedIndex(0)
  }, [])

  const close = useCallback(() => {
    setIsOpen(false)
    setQuery('')
    setSelectedIndex(0)
  }, [])

  const toggle = useCallback(() => {
    setIsOpen(current => !current)
    setSelectedIndex(0)
  }, [])

  useEffect(() => {
    function onKeyDown(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        toggle()
        return
      }
      if (!isOpen) return
      if (event.key === 'Escape') {
        event.preventDefault()
        close()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [close, isOpen, toggle])

  return {
    isOpen,
    query,
    selectedIndex,
    setQuery,
    setSelectedIndex,
    open,
    close,
    toggle,
  }
}
