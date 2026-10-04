import { AlertTriangle, Check, Clock, Loader2, MousePointerClick, X } from 'lucide-react'
import { humanize } from '../../lib/format'
import type { Activity, Block, Turn } from '../../types/chat'
import { UIRenderer } from '../genui/UIRenderer'
import { Markdown } from '../ui/primitives'

export function UserTurn({ turn }: { turn: Turn }) {
  return (
    <div className="flex animate-fade-in justify-end">
      <div className="flex max-w-[85%] flex-col items-end gap-2">
        {turn.blocks.map((block, i) =>
          block.type === 'event' ? (
            <div
              key={i}
              className="inline-flex items-center gap-2 rounded-full border border-brand/30 bg-brand/10 px-3 py-1.5 text-sm text-brand"
            >
              <MousePointerClick className="size-3.5" />
              {block.label || humanize(block.action)}
            </div>
          ) : block.type === 'text' ? (
            <div
              key={i}
              className="rounded-2xl rounded-br-md bg-surface-3 px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap"
            >
              {block.text}
            </div>
          ) : null,
        )}
      </div>
    </div>
  )
}

interface AssistantTurnProps {
  turn: Turn
  live: boolean
  activities: Activity[]
  status: string | null
}

export function AssistantTurn({ turn, live, activities, status }: AssistantTurnProps) {
  const empty = turn.blocks.length === 0
  return (
    <div className="flex animate-fade-in gap-3">
      <img src="/favicon.svg" alt="" className="mt-0.5 size-7 shrink-0" />
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        {live && (activities.length > 0 || status) && (
          <ActivityList activities={activities} status={status} />
        )}
        {turn.blocks.map((block, i) => (
          <BlockView key={block.type === 'ui' ? block.id : i} block={block} />
        ))}
        {live && empty && activities.length === 0 && !status && (
          <p className="shimmer-text pt-1 text-sm font-medium">Thinking…</p>
        )}
        {live && !empty && activities.every((a) => a.state !== 'running') && !status && (
          <p className="shimmer-text text-sm font-medium">Composing…</p>
        )}
      </div>
    </div>
  )
}

function BlockView({ block }: { block: Block }) {
  switch (block.type) {
    case 'text':
      return block.text.trim() ? <Markdown>{block.text}</Markdown> : null
    case 'ui':
      return <UIRenderer components={block.components} />
    case 'error':
      return (
        <div className="flex items-start gap-2.5 rounded-xl border border-bad/30 bg-bad/10 px-4 py-3 text-sm text-bad">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>{block.message}</span>
        </div>
      )
    default:
      return null
  }
}

function ActivityList({ activities, status }: { activities: Activity[]; status: string | null }) {
  return (
    <div className="flex flex-wrap gap-2">
      {activities.map((a) => (
        <span
          key={a.id}
          className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-muted"
        >
          {a.state === 'running' && <Loader2 className="size-3 animate-spin text-brand" />}
          {a.state === 'done' && <Check className="size-3 text-good" />}
          {a.state === 'failed' && <X className="size-3 text-bad" />}
          {a.label}
        </span>
      ))}
      {status && (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-warn/30 bg-warn/10 px-2.5 py-1 text-xs text-warn">
          <Clock className="size-3" />
          {status}
        </span>
      )}
    </div>
  )
}
