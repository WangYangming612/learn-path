/**
 * 反馈 API
 * 对齐 backend/app/api/v1/feedback.py
 *
 * POST /feedback/start → text/event-stream（question_chunk / question_done / error）
 * POST /feedback/reply → JSON FeedbackReplyResponse
 */

import api, { getStoredToken } from "./api";
import type {
  FeedbackReplyRequest,
  FeedbackReplyResponse,
  FeedbackStreamEvent,
} from "@/types";
import { readSSEStream } from "@/utils/sse";

/**
 * 启动反馈流程并消费 SSE 流
 * @returns session_id（question_done 携带）
 */
export async function startFeedbackStream(
  taskId: string,
  onEvent: (event: FeedbackStreamEvent) => void,
  signal?: AbortSignal
): Promise<string> {
  const token = getStoredToken();
  const response = await fetch("/api/v1/feedback/start", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ task_id: String(taskId) }),
    signal,
  });

  if (response.status === 401) {
    throw new Error("登录已过期，请重新登录");
  }

  if (!response.ok) {
    let detail = `启动反馈失败（${response.status}）`;
    try {
      const errBody = (await response.json()) as { detail?: string };
      if (errBody.detail) detail = String(errBody.detail);
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  if (!response.body) {
    throw new Error("浏览器不支持流式响应");
  }

  let sessionId = "";

  await readSSEStream(response.body, (raw) => {
    let parsed: FeedbackStreamEvent;
    try {
      parsed = JSON.parse(raw) as FeedbackStreamEvent;
    } catch {
      return;
    }

    onEvent(parsed);

    if (parsed.type === "question_done" && parsed.session_id) {
      sessionId = parsed.session_id;
    }
  }, signal);

  if (signal?.aborted) {
    const err = new Error("Aborted");
    err.name = "AbortError";
    throw err;
  }

  if (!sessionId) {
    throw new Error("未收到反馈会话 ID，请稍后重试");
  }

  return sessionId;
}

/** POST /feedback/reply */
export async function replyFeedback(
  payload: FeedbackReplyRequest
): Promise<FeedbackReplyResponse> {
  const { data } = await api.post<FeedbackReplyResponse>("/feedback/reply", {
    session_id: payload.session_id,
    reply: payload.reply,
  });
  return data;
}
