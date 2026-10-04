import { AlertTriangle, Loader2, Menu } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Composer } from './components/chat/Composer'
import { EmptyState } from './components/chat/EmptyState'
import { AssistantTurn, UserTurn } from './components/chat/Messages'
import { ActionProvider } from './components/genui/ActionContext'
import { Logo, Sidebar } from './components/layout/Sidebar'
import { useChat } from './hooks/useChat'
import { useConversations } from './hooks/useConversations'
import { api } from './lib/api'
import type { Health, UIEventInput } from './types/chat'

export default function App() {
  const { conversations, refresh, remove } = useConversations()
  const chat = useChat({ onTurnComplete: refresh })
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [health, setHealth] = useState<Health | null>(null)
  const [backendDown, setBackendDown] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setBackendDown(true))
  }, [])

  // Keep the view pinned to the newest content unless the user scrolled up.
  useEffect(() => {
    const el = scrollRef.current
    if (el && stickToBottom.current && chat.turns.length > 0) el.scrollTo({ top: el.scrollHeight })
  }, [chat.turns, chat.activities, chat.status])

  const onScroll = () => {
    const el = scrollRef.current
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120
  }

  const sendMessage = useCallback(
    (message: string) => {
      stickToBottom.current = true
      void chat.send({ message })
    },
    [chat],
  )

  const dispatchEvent = useCallback(
    (event: UIEventInput) => {
      stickToBottom.current = true
      void chat.send({ event })
    },
    [chat],
  )

  const selectConversation = (id: string) => {
    setSidebarOpen(false)
    if (id !== chat.conversationId) void chat.load(id)
  }

  const deleteConversation = (id: string) => {
    if (id === chat.conversationId) chat.reset()
    void remove(id)
  }

  const isEmpty = chat.turns.length === 0
  const lastIndex = chat.turns.length - 1

  return (
    <div className="flex h-full">
      <Sidebar
        conversations={conversations}
        activeId={chat.conversationId}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNew={() => {
          chat.reset()
          setSidebarOpen(false)
        }}
        onSelect={selectConversation}
        onDelete={deleteConversation}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-border px-4 py-3 md:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
            className="grid size-9 place-items-center rounded-lg border border-border text-muted hover:bg-surface-2"
          >
            <Menu className="size-4" />
          </button>
          <Logo />
        </header>

        {(backendDown || (health && !health.llm_configured)) && (
          <div className="flex items-center gap-2 border-b border-warn/30 bg-warn/10 px-4 py-2 text-sm text-warn">
            <AlertTriangle className="size-4 shrink-0" />
            {backendDown
              ? 'Cannot reach the FitGen API. Is the backend running?'
              : 'GROQ_API_KEY is not configured on the server — chat is disabled.'}
          </div>
        )}

        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto">
          {chat.isLoading ? (
            <div className="grid h-full place-items-center text-muted">
              <Loader2 className="size-5 animate-spin" />
            </div>
          ) : isEmpty ? (
            <EmptyState onPick={sendMessage} />
          ) : (
            <ActionProvider dispatch={dispatchEvent} disabled={chat.isStreaming}>
              <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-8">
                {chat.turns.map((turn, i) =>
                  turn.role === 'user' ? (
                    <UserTurn key={turn.id} turn={turn} />
                  ) : (
                    <AssistantTurn
                      key={turn.id}
                      turn={turn}
                      live={chat.isStreaming && i === lastIndex}
                      activities={chat.activities}
                      status={chat.status}
                    />
                  ),
                )}
              </div>
            </ActionProvider>
          )}
        </div>

        <div className="mx-auto w-full max-w-3xl px-4 pb-4">
          <Composer
            onSend={sendMessage}
            onStop={chat.stop}
            isStreaming={chat.isStreaming}
            autoFocus
          />
          <p className="mt-2 text-center text-[11px] text-subtle">
            {health ? `${health.model} on Groq · ` : ''}General fitness guidance, not medical advice.
          </p>
        </div>
      </main>
    </div>
  )
}
