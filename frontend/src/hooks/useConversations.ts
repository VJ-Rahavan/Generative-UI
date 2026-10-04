import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { ConversationSummary } from '../types/chat'

export function useConversations() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setConversations(await api.listConversations())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversations')
    }
  }, [])

  const remove = useCallback(async (id: string) => {
    setConversations((prev) => prev.filter((c) => c.id !== id)) // optimistic
    try {
      await api.deleteConversation(id)
    } catch {
      await refresh()
    }
  }, [refresh])

  useEffect(() => {
    let cancelled = false
    api
      .listConversations()
      .then((items) => !cancelled && setConversations(items))
      .catch((err: Error) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [])

  return { conversations, error, refresh, remove }
}
