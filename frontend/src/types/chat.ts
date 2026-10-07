import type { UINode } from './ui'

export interface TextBlock {
  type: 'text'
  text: string
}

export interface UIBlock {
  type: 'ui'
  id: string
  components: UINode[]
  /** Client-only: more components are still being generated. */
  streaming?: boolean
}

export interface EventBlock {
  type: 'event'
  action: string
  payload: Record<string, unknown>
  label?: string | null
}

/** Client-only: an error shown inline in the assistant turn. */
export interface ErrorBlock {
  type: 'error'
  message: string
}

export type Block = TextBlock | UIBlock | EventBlock | ErrorBlock

export interface Turn {
  id: string
  role: 'user' | 'assistant'
  blocks: Block[]
}

export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends ConversationSummary {
  turns: Omit<Turn, 'id'>[]
}

export interface UIEventInput {
  action: string
  payload: Record<string, unknown>
  label?: string
}

export type ChatInput = { message: string } | { event: UIEventInput }

/** Server-Sent Events emitted by POST /api/chat (see backend agent/events.py). */
export type StreamEvent =
  | { event: 'conversation'; data: { conversation_id: string; title: string } }
  | { event: 'text'; data: { delta: string } }
  | { event: 'tool_start'; data: { id: string; name: string; label: string } }
  | { event: 'tool_end'; data: { id: string; name: string; ok: boolean } }
  | { event: 'ui_start'; data: { id: string } }
  | { event: 'ui_component'; data: { id: string; component: UINode } }
  | { event: 'ui_end'; data: { id: string } }
  | { event: 'status'; data: { message: string } }
  | { event: 'error'; data: { message: string; code?: string | null } }
  | { event: 'done'; data: Record<string, never> }

export interface Activity {
  id: string
  label: string
  state: 'running' | 'done' | 'failed'
}

export interface Health {
  status: 'ok'
  app: string
  model: string
  llm_configured: boolean
}
