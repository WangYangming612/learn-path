/**
 * 路由守卫
 * 未登录跳转 /login；未初始化时展示加载态
 */

import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Spin } from "antd";
import { useAuth } from "@/hooks/useAuth";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { isAuthenticated, initialized } = useAuth();
  const location = useLocation();

  if (!initialized) {
    return (
      <div className="app-boot-screen">
        <Spin size="large" tip="正在恢复会话…" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <Navigate
        to={`/login?redirect=${encodeURIComponent(location.pathname)}`}
        replace
      />
    );
  }

  return <>{children}</>;
};

export default ProtectedRoute;
