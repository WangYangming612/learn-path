/**
 * SSE 工具与全局事件钩子
 *
 * - useSSE：可选接入 GET /events/stream（后端尚未实现时静默失败）
 * - readSSEStream 见 @/utils/sse（供 feedback 流式接口使用）
 */

import { useEffect, useRef, useState } from "react";
import { getStoredToken } from "@/services/api";

export type SSEHandler = (eventType: string, data: unknown) => void;

export { readSSEStream } from "@/utils/sse";

interface UseSSEOptions {
  /** 是否启用全局 SSE（默认 false，等 /events/stream 可用后再开） */
  enabled?: boolean;
  onEvent?: SSEHandler;
}

/**
 * 全局 EventSource 钩子（契约：GET /api/v1/events/stream?token=）
 * 当前后端未挂载该路由时保持断开，不影响页面。
 */
export function useSSE(options: UseSSEOptions = {}) {
  const { enabled = false, onEvent } = options;
  const [connected, setConnected] = useState(false);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    if (!enabled) return;

    const token = getStoredToken();
    if (!token) return;

    let es: EventSource | null = null;
    let closed = false;

    try {
      es = new EventSource(`/api/v1/events/stream?token=${encodeURIComponent(token)}`);
    } catch {
      return;
    }

    const notify = (type: string) => (e: MessageEvent) => {
      if (closed) return;
      let payload: unknown = e.data;
      try {
        payload = JSON.parse(e.data);
      } catch {
        // keep raw string
      }
      handlerRef.current?.(type, payload);
    };

    es.onopen = () => {
      if (!closed) setConnected(true);
    };

    es.onerror = () => {
      if (!closed) setConnected(false);
    };

    es.addEventListener("schedule_updated", notify("schedule_updated"));
    es.addEventListener("feedback_stream", notify("feedback_stream"));
    es.addEventListener("weekly_report", notify("weekly_report"));
    es.addEventListener("intervention", notify("intervention"));
    es.onmessage = notify("message");

    return () => {
      closed = true;
      setConnected(false);
      es?.close();
    };
  }, [enabled]);

  return { connected };
}

export default useSSE;
