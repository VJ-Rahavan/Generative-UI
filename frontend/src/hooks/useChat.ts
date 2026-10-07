import { useCallback, useRef, useState } from 'react'
import { api } from '../lib/api'
import { uid } from '../lib/format'
import type { Activity, Block, ChatInput, Turn } from '../types/chat'

/** Mark UI blocks complete (one by id, or all) and drop blocks that ended up empty. */
function closeUIBlocks(blocks: Block[], id?: string): Block[] {
  return blocks
    .map((b) => (b.type === 'ui' && (!id || b.id === id) ? { ...b, streaming: false } : b))
    .filter((b) => b.type !== 'ui' || b.streaming || b.components.length > 0)
}

interface UseChatOptions {
  /** Called when a turn finishes (e.g. to refresh the conversation list). */
  onTurnComplete?: () => void
}

/** Chat state machine: turns, streaming progress and the active conversation. */
export function useChat({ onTurnComplete }: UseChatOptions = {}) {
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [activities, setActivities] = useState<Activity[]>([])
  const [status, setStatus] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  const abortRef = useRef<AbortController | null>(null)
  const conversationRef = useRef<string | null>(null)

  const updateAssistant = useCallback((update: (blocks: Block[]) => Block[]) => {
    setTurns((prev) => {
      const last = prev.at(-1)
      if (!last || last.role !== 'assistant') return prev
      return [...prev.slice(0, -1), { ...last, blocks: update(last.blocks) }]
    })
  }, [])

  const appendError = useCallback(
    (message: string) => updateAssistant((blocks) => [...blocks, { type: 'error', message }]),
    [updateAssistant],
  )

  const send = useCallback(
    async (input: ChatInput) => {
      if (abortRef.current) return // one turn at a time

      const userBlock: Block =
        'message' in input
          ? { type: 'text', text: input.message }
          : { type: 'event', ...input.event }
      setTurns((prev) => [
        ...prev,
        { id: uid(), role: 'user', blocks: [userBlock] },
        { id: uid(), role: 'assistant', blocks: [] },
      ])
      setActivities([])
      setStatus(null)
      setIsStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller
      try {
        const stream = api.chat(
          { ...input, conversation_id: conversationRef.current },
          controller.signal,
        )
        for await (const ev of stream) {
          switch (ev.event) {
            case 'conversation':
              conversationRef.current = ev.data.conversation_id
              setConversationId(ev.data.conversation_id)
              break
            case 'text':
              setStatus(null)
              updateAssistant((blocks) => {
                const last = blocks.at(-1)
                return last?.type === 'text'
                  ? [...blocks.slice(0, -1), { ...last, text: last.text + ev.data.delta }]
                  : [...blocks, { type: 'text', text: ev.data.delta }]
              })
              break
            case 'tool_start':
              setStatus(null)
              setActivities((prev) => [
                ...prev,
                { id: ev.data.id, label: ev.data.label, state: 'running' },
              ])
              break
            case 'tool_end':
              setActivities((prev) =>
                prev.map((a) =>
                  a.id === ev.data.id ? { ...a, state: ev.data.ok ? 'done' : 'failed' } : a,
                ),
              )
              break
            case 'ui_start':
              setStatus(null)
              updateAssistant((blocks) => [
                ...blocks,
                { type: 'ui', id: ev.data.id, components: [], streaming: true },
              ])
              break
            case 'ui_component':
              // Streamed UI: each component is appended the moment it has been generated.
              updateAssistant((blocks) =>
                blocks.map((b) =>
                  b.type === 'ui' && b.id === ev.data.id
                    ? { ...b, components: [...b.components, ev.data.component] }
                    : b,
                ),
              )
              break
            case 'ui_end':
              updateAssistant((blocks) => closeUIBlocks(blocks, ev.data.id))
              break
            case 'status':
              setStatus(ev.data.message)
              break
            case 'error':
              appendError(ev.data.message)
              break
          }
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          appendError(err instanceof Error ? err.message : 'Connection lost.')
        }
      } finally {
        updateAssistant((blocks) => closeUIBlocks(blocks))
        abortRef.current = null
        setIsStreaming(false)
        setStatus(null)
        onTurnComplete?.()
      }
    },
    [appendError, onTurnComplete, updateAssistant],
  )

  const stop = useCallback(() => abortRef.current?.abort(), [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    conversationRef.current = null
    setConversationId(null)
    setTurns([])
    setActivities([])
  }, [])

  const load = useCallback(async (id: string) => {
    abortRef.current?.abort()
    setIsLoading(true)
    try {
      const detail = await api.getConversation(id)
      conversationRef.current = id
      setConversationId(id)
      setTurns(detail.turns.map((t) => ({ ...t, id: uid() })))
      setActivities([])
    } finally {
      setIsLoading(false)
    }
  }, [])

  return {
    conversationId,
    turns,
    activities,
    status,
    isStreaming,
    isLoading,
    send,
    stop,
    reset,
    load,
  }
}
