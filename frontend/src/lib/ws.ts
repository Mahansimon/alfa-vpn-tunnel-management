/** اتصال WebSocket با اتصال مجدد نمایی. احراز هویت با کوکی نشست انجام می‌شود. */
export type WsHandler = (event: string, data: unknown) => void

export class LiveSocket {
  private socket: WebSocket | null = null
  private retries = 0
  private closed = false
  private timer: ReturnType<typeof setTimeout> | null = null
  private ping: ReturnType<typeof setInterval> | null = null

  constructor(
    private topic: string,
    private handler: WsHandler,
  ) {}

  connect() {
    if (this.closed) return
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${protocol}://${window.location.host}/api/v1/ws?topic=${encodeURIComponent(this.topic)}`
    try {
      this.socket = new WebSocket(url)
    } catch {
      this.scheduleReconnect()
      return
    }
    this.socket.onopen = () => {
      this.retries = 0
      this.handler('socket.open', { topic: this.topic })
      this.ping = setInterval(() => this.socket?.readyState === 1 && this.socket.send('ping'), 25000)
    }
    this.socket.onmessage = (message) => {
      try {
        const payload = JSON.parse(message.data as string)
        this.handler(payload.event, payload.data)
      } catch {
        /* پیام نامعتبر نادیده گرفته می‌شود */
      }
    }
    this.socket.onclose = () => {
      if (this.ping) clearInterval(this.ping)
      this.handler('socket.close', { topic: this.topic })
      this.scheduleReconnect()
    }
    this.socket.onerror = () => this.socket?.close()
  }

  private scheduleReconnect() {
    if (this.closed) return
    this.retries += 1
    const delay = Math.min(30000, 1000 * 2 ** Math.min(this.retries, 5))
    this.timer = setTimeout(() => this.connect(), delay)
  }

  close() {
    this.closed = true
    if (this.timer) clearTimeout(this.timer)
    if (this.ping) clearInterval(this.ping)
    this.socket?.close()
  }
}
