/**
 * 认证 Hook
 *
 * What: 封装 authStore，提供登录/注册/登出与便捷派生状态
 * Why: 页面层统一通过 Hook 访问，避免直接依赖 store 细节
 */

import { useCallback } from "react";
import { useAuthStore } from "@/stores/authStore";
import type { LoginRequest, RegisterRequest } from "@/types";

export function useAuth() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const loading = useAuthStore((s) => s.loading);
  const initialized = useAuthStore((s) => s.initialized);
  const loginAction = useAuthStore((s) => s.login);
  const registerAction = useAuthStore((s) => s.register);
  const logoutAction = useAuthStore((s) => s.logout);
  const initialize = useAuthStore((s) => s.initialize);

  const isAuthenticated = Boolean(token && user);

  const login = useCallback(
    (payload: LoginRequest) => loginAction(payload),
    [loginAction]
  );

  const register = useCallback(
    (payload: RegisterRequest) => registerAction(payload),
    [registerAction]
  );

  const logout = useCallback(() => {
    logoutAction();
  }, [logoutAction]);

  return {
    token,
    user,
    loading,
    initialized,
    isAuthenticated,
    login,
    register,
    logout,
    initialize,
  };
}
