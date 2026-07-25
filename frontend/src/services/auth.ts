/**
 * 认证相关 API
 *
 * 兼容两种后端形态：
 * - 当前实现：OAuth2 表单登录 + 裸响应 + GET /auth/me
 * - 契约：JSON 登录 + 包装响应 + GET /auth/profile
 */

import api from "./api";
import {
  normalizeUser,
  type BackendUserRaw,
  type LoginRequest,
  type LoginResponse,
  type RegisterRequest,
  type UserInfo,
} from "@/types";

/** 注册 */
export async function register(payload: RegisterRequest): Promise<UserInfo> {
  const { data } = await api.post<BackendUserRaw>("/auth/register", payload);
  return normalizeUser(data);
}

/**
 * 登录
 * 当前后端使用 OAuth2PasswordRequestForm（x-www-form-urlencoded）
 * 同时保留 JSON 回退以兼容契约文档
 */
export async function login(payload: LoginRequest): Promise<LoginResponse> {
  const form = new URLSearchParams();
  form.append("username", payload.username);
  form.append("password", payload.password);

  try {
    const { data } = await api.post<LoginResponse>("/auth/login", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    return data;
  } catch (formError) {
    // 仅在表单格式不被接受时回退 JSON（契约后端）
    const msg = formError instanceof Error ? formError.message : "";
    const maybeWrongFormat =
      /422|参数|content|unprocessable|field required/i.test(msg);

    if (!maybeWrongFormat) {
      throw formError;
    }

    const { data } = await api.post<LoginResponse>("/auth/login", payload);
    return data;
  }
}

/**
 * 获取当前用户
 * 优先 /auth/me（当前后端），回退 /auth/profile（契约）
 */
export async function fetchCurrentUser(): Promise<UserInfo> {
  try {
    const { data } = await api.get<BackendUserRaw>("/auth/me");
    return normalizeUser(data);
  } catch {
    const { data } = await api.get<BackendUserRaw>("/auth/profile");
    return normalizeUser(data);
  }
}
