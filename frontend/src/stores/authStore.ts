/**
 * 认证状态 Store (Zustand)
 *
 * What: 管理 token、用户信息、加载态
 * Why: 全局共享登录态，刷新后可从 localStorage 恢复
 */

import { create } from "zustand";
import {
  clearStoredToken,
  getStoredToken,
  setStoredToken,
} from "@/services/api";
import * as authApi from "@/services/auth";
import type { LoginRequest, RegisterRequest, UserInfo } from "@/types";

interface AuthState {
  token: string | null;
  user: UserInfo | null;
  loading: boolean;
  initialized: boolean;

  /** 应用启动时从本地恢复会话 */
  initialize: () => Promise<void>;
  login: (payload: LoginRequest) => Promise<void>;
  register: (payload: RegisterRequest) => Promise<void>;
  logout: () => void;
  setUser: (user: UserInfo | null) => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: getStoredToken(),
  user: null,
  loading: false,
  initialized: false,

  initialize: async () => {
    const token = getStoredToken();
    if (!token) {
      set({ token: null, user: null, initialized: true });
      return;
    }

    set({ loading: true, token });
    try {
      const user = await authApi.fetchCurrentUser();
      set({ user, loading: false, initialized: true });
    } catch {
      clearStoredToken();
      set({ token: null, user: null, loading: false, initialized: true });
    }
  },

  login: async (payload) => {
    set({ loading: true });
    try {
      const result = await authApi.login(payload);
      setStoredToken(result.access_token);

      let user = result.user ?? null;
      if (!user) {
        user = await authApi.fetchCurrentUser();
      }

      set({
        token: result.access_token,
        user,
        loading: false,
        initialized: true,
      });
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  register: async (payload) => {
    set({ loading: true });
    try {
      await authApi.register(payload);
      // 注册成功后自动登录
      await get().login({
        username: payload.username,
        password: payload.password,
      });
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  logout: () => {
    clearStoredToken();
    set({ token: null, user: null, loading: false });
  },

  setUser: (user) => set({ user }),
}));
