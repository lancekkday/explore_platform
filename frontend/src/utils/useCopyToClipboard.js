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
    if (text == null) return false
    const str = String(text)
    // navigator.clipboard is undefined on insecure (HTTP) origins / older browsers,
    // so try it first, then fall back to a hidden-textarea execCommand copy.
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(str)
        setCopied(true)
        return true
      }
    } catch { /* fall through to execCommand */ }
    try {
      const ta = document.createElement('textarea')
      ta.value = str
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(ta)
      if (ok) {
        setCopied(true)
        return true
      }
    } catch (err) {
      console.warn('clipboard copy failed:', err)
    }
    return false
  }

  return [copied, copy]
}
