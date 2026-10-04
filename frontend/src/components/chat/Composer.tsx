import { ArrowUp, Square } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { cn } from '../../lib/format'

interface ComposerProps {
  onSend: (message: string) => void
  onStop: () => void
  isStreaming: boolean
  autoFocus?: boolean
}

export function Composer({ onSend, onStop, isStreaming, autoFocus }: ComposerProps) {
  const [value, setValue] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  // Auto-grow up to ~8 lines
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [value])

  const submit = () => {
    const text = value.trim()
    if (!text || isStreaming) return
    onSend(text)
    setValue('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="rounded-2xl border border-border-strong bg-surface-2 p-2 shadow-lg shadow-black/20 focus-within:border-brand/50">
      <div className="flex items-end gap-2">
        <textarea
          ref={ref}
          rows={1}
          value={value}
          autoFocus={autoFocus}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about your training, log a workout, plan a program…"
          aria-label="Message"
          className="max-h-[200px] flex-1 resize-none bg-transparent px-2.5 py-2 text-[15px] text-fg outline-none placeholder:text-subtle"
        />
        <button
          type="button"
          onClick={isStreaming ? onStop : submit}
          disabled={!isStreaming && !value.trim()}
          aria-label={isStreaming ? 'Stop' : 'Send'}
          className={cn(
            'grid size-9 shrink-0 place-items-center rounded-xl transition-colors',
            isStreaming
              ? 'bg-surface-3 text-fg hover:bg-border-strong'
              : 'bg-brand text-brand-fg hover:bg-brand-dim disabled:bg-surface-3 disabled:text-subtle',
          )}
        >
          {isStreaming ? <Square className="size-3.5 fill-current" /> : <ArrowUp className="size-4" />}
        </button>
      </div>
    </div>
  )
}
