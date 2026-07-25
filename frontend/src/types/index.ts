/**
 * 前端 TypeScript 类型定义
 * 对齐 docs/contracts/frontend-types.md，并兼容当前后端字段差异
 */

/** 全局 API 响应包装（契约格式） */
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T | null;
}

/** 分页响应 */
export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** 用户信息 */
export interface UserInfo {
  user_id: string;
  username: string;
  email: string | null;
  daily_available_minutes: number;
  is_active: boolean;
  created_at: string;
}

/** 登录响应 */
export interface LoginResponse {
  access_token: string;
  token_type: "bearer" | string;
  expires_in?: number;
  user?: UserInfo;
}

/** 注册请求 */
export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

/** 登录请求 */
export interface LoginRequest {
  username: string;
  password: string;
}

/** 后端原始用户响应（id 为 number） */
export interface BackendUserRaw {
  id?: number | string;
  user_id?: string;
  username: string;
  email?: string | null;
  daily_available_minutes?: number;
  is_active?: boolean;
  created_at?: string;
}

/** 将后端用户字段归一化为前端 UserInfo */
export function normalizeUser(raw: BackendUserRaw): UserInfo {
  const id = raw.user_id ?? (raw.id != null ? String(raw.id) : "");
  return {
    user_id: id,
    username: raw.username,
    email: raw.email ?? null,
    daily_available_minutes: raw.daily_available_minutes ?? 90,
    is_active: raw.is_active ?? true,
    created_at: raw.created_at ?? new Date().toISOString(),
  };
}
