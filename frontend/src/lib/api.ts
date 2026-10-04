import type {
  ChatInput,
  ConversationDetail,
  ConversationSummary,
  Health,
  StreamEvent,
} from '../types/chat'
import { readSSE } from './sse'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function errorFrom(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status})`
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') message = body.detail
    else if (Array.isArray(body?.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join('; ')
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, message)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) throw await errorFrom(res)
  return (res.status === 204 ? undefined : await res.json()) as T
}

export const api = {
  health: () => request<Health>('/health'),

  listConversations: () => request<ConversationSummary[]>('/conversations'),

  getConversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),

  deleteConversation: (id: string) =>
    request<void>(`/conversations/${id}`, { method: 'DELETE' }),

  /** Run one assistant turn, yielding typed stream events as they arrive. */
  async *chat(
    input: ChatInput & { conversation_id?: string | null },
    signal?: AbortSignal,
  ): AsyncGenerator<StreamEvent> {
    const res = await fetch(`${BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(input),
      signal,
    })
    if (!res.ok || !res.body) throw await errorFrom(res)
    for await (const message of readSSE(res.body)) {
      yield { event: message.event, data: JSON.parse(message.data) } as StreamEvent
    }
  },
}
