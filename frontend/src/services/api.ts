/**
 * Axios 实例与拦截器
 *
 * What: 统一 HTTP 客户端，注入 Token，处理 401
 * Why: 避免每个请求手动加 Header；未登录/过期统一跳转登录页
 */

import axios, {
  type AxiosError,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import type { ApiResponse } from "@/types";

const TOKEN_KEY = "learnpath_token";

/** 读取本地 Token */
export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/** 写入本地 Token */
export function setStoredToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

/** 清除本地 Token */
export function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * 判断是否为契约包装响应 { code, message, data }
 */
function isApiEnvelope(payload: unknown): payload is ApiResponse<unknown> {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "code" in payload &&
    "message" in payload &&
    "data" in payload
  );
}

const api = axios.create({
  baseURL: "/api/v1",
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

/** 请求拦截：注入 Bearer Token */
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getStoredToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

/**
 * 响应拦截：
 * 1. 若为契约包装格式，code !== 0 时抛错
 * 2. HTTP 401 清除登录态并跳转
 */
api.interceptors.response.use(
  (response: AxiosResponse) => {
    const payload = response.data;

    if (isApiEnvelope(payload)) {
      if (payload.code !== 0) {
        const err = new Error(payload.message || "请求失败") as Error & {
          code?: number;
        };
        err.code = payload.code;
        return Promise.reject(err);
      }
      // 解包后下游拿到 data
      response.data = payload.data;
    }

    return response;
  },
  (error: AxiosError<{ detail?: unknown; message?: string }>) => {
    const status = error.response?.status;

    if (status === 401) {
      clearStoredToken();
      // 避免在登录页循环跳转
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = `/login?redirect=${encodeURIComponent(
          window.location.pathname
        )}`;
      }
    }

    const raw = error.response?.data?.detail ?? error.response?.data?.message;
    let detail = "网络异常，请稍后重试";

    if (typeof raw === "string") {
      detail = raw;
    } else if (Array.isArray(raw) && raw.length > 0) {
      // FastAPI 校验错误数组
      const first = raw[0] as { msg?: string };
      detail = first?.msg || "请求参数错误";
    } else if (error.message) {
      detail = error.message;
    }

    return Promise.reject(new Error(detail));
  }
);

export default api;
