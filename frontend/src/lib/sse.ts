export interface SSEMessage {
  event: string
  data: string
}

/**
 * Parse a Server-Sent Events byte stream. Used instead of EventSource because the chat
 * endpoint is a POST. Handles CRLF/LF line endings, multi-line data and comment pings.
 */
export async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<SSEMessage> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // Normalize line endings, but hold back a trailing "\r" whose "\n" may be in the next chunk.
      const heldCR = buffer.endsWith('\r')
      buffer = (heldCR ? buffer.slice(0, -1) : buffer).replace(/\r\n?/g, '\n') + (heldCR ? '\r' : '')
      let boundary: number
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const message = parseMessage(buffer.slice(0, boundary))
        buffer = buffer.slice(boundary + 2)
        if (message) yield message
      }
    }
    const tail = parseMessage(buffer)
    if (tail) yield tail
  } finally {
    reader.releaseLock()
  }
}

function parseMessage(raw: string): SSEMessage | null {
  let event = 'message'
  const data: string[] = []
  for (const line of raw.split('\n')) {
    if (!line || line.startsWith(':')) continue
    const sep = line.indexOf(':')
    const field = sep === -1 ? line : line.slice(0, sep)
    const value = sep === -1 ? '' : line.slice(sep + 1).replace(/^ /, '')
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
  }
  return data.length ? { event, data: data.join('\n') } : null
}
