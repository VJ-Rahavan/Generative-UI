import { MessageSquare, Plus, Trash2, X } from 'lucide-react'
import { cn, relativeTime } from '../../lib/format'
import type { ConversationSummary } from '../../types/chat'

interface SidebarProps {
  conversations: ConversationSummary[]
  activeId: string | null
  open: boolean
  onClose: () => void
  onNew: () => void
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}

export function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <img src="/favicon.svg" alt="" className="size-8" />
      <div className="leading-tight">
        <p className="font-semibold tracking-tight">FitGen</p>
        <p className="text-[11px] text-muted">AI training partner</p>
      </div>
    </div>
  )
}

export function Sidebar({
  conversations,
  activeId,
  open,
  onClose,
  onNew,
  onSelect,
  onDelete,
}: SidebarProps) {
  return (
    <>
      {/* Mobile backdrop */}
      <div
        onClick={onClose}
        className={cn(
          'fixed inset-0 z-30 bg-black/60 backdrop-blur-sm transition-opacity md:hidden',
          open ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
      />
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-border bg-surface transition-transform md:static md:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex items-center justify-between px-4 pt-4 pb-3">
          <Logo />
          <button
            onClick={onClose}
            aria-label="Close sidebar"
            className="grid size-8 place-items-center rounded-lg text-muted hover:bg-surface-2 md:hidden"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="px-3">
          <button
            onClick={onNew}
            className="flex h-10 w-full items-center gap-2 rounded-xl bg-brand px-3 text-sm font-semibold text-brand-fg transition-colors hover:bg-brand-dim"
          >
            <Plus className="size-4" /> New chat
          </button>
        </div>

        <p className="px-5 pt-5 pb-2 text-[11px] font-semibold tracking-wider text-subtle uppercase">
          Recent
        </p>
        <nav className="flex-1 overflow-y-auto px-2 pb-4">
          {conversations.length === 0 && (
            <p className="px-3 py-2 text-sm text-subtle">No conversations yet.</p>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              className={cn(
                'group relative flex items-center rounded-lg transition-colors',
                c.id === activeId ? 'bg-surface-3' : 'hover:bg-surface-2',
              )}
            >
              <button
                onClick={() => onSelect(c.id)}
                className="flex min-w-0 flex-1 items-center gap-2.5 px-3 py-2 text-left"
              >
                <MessageSquare
                  className={cn('size-4 shrink-0', c.id === activeId ? 'text-brand' : 'text-subtle')}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{c.title}</span>
                  <span className="block text-[11px] text-subtle">{relativeTime(c.updated_at)}</span>
                </span>
              </button>
              <button
                onClick={() => {
                  if (window.confirm(`Delete “${c.title}”?`)) onDelete(c.id)
                }}
                aria-label={`Delete ${c.title}`}
                className="mr-1.5 grid size-7 shrink-0 place-items-center rounded-md text-subtle opacity-0 transition-opacity group-hover:opacity-100 hover:bg-bad/15 hover:text-bad focus:opacity-100"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </nav>
      </aside>
    </>
  )
}
