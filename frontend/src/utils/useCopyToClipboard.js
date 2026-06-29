import { useState, useEffect } from 'react'

/**
 * Copy-to-clipboard with transient "copied" feedback.
 * Returns [copied, copy] — `copy(text)` writes to the clipboard and flips `copied`
 * true for `resetMs`. Shared by RunStatusBar's run_id button and FilterBar's
 * request_id chip so the clipboard + feedback logic lives in one place.
 */
export function useCopyToClipboard(resetMs = 1500) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const t = setTimeout(() => setCopied(false), resetMs)
    return () => clearTimeout(t)
  }, [copied, resetMs])

  const copy = async (text) => {
    if (text == null) return
    try {
      await navigator.clipboard.writeText(String(text))
      setCopied(true)
    } catch (err) {
      console.warn('clipboard write failed:', err)
    }
  }

  return [copied, copy]
}
