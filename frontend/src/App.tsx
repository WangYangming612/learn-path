/**
 * 根组件 — 路由 + 主题 + 会话初始化
 */

import React, { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { App as AntApp, ConfigProvider, Spin } from "antd";
import zhCN from "antd/locale/zh_CN";
import AppLayout from "@/components/Layout";
import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuth } from "@/hooks/useAuth";
import DashboardPage from "@/pages/Dashboard";
import LoginPage from "@/pages/Login";
import RegisterPage from "@/pages/Register";

const theme = {
  token: {
    colorPrimary: "#0f766e",
    colorInfo: "#0e7490",
    colorSuccess: "#059669",
    colorWarning: "#d97706",
    colorError: "#dc2626",
    borderRadius: 12,
    fontFamily:
      '"Plus Jakarta Sans", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
    controlHeightLG: 44,
  },
  components: {
    Button: {
      primaryShadow: "0 8px 20px rgba(15, 118, 110, 0.25)",
      fontWeight: 600,
    },
    Input: {
      activeBorderColor: "#0f766e",
      hoverBorderColor: "#14b8a6",
    },
    Menu: {
      itemBorderRadius: 10,
      itemMarginInline: 10,
      itemHeight: 44,
    },
  },
};

/** 已登录访问登录/注册时跳回 Dashboard */
const GuestOnly: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, initialized } = useAuth();

  if (!initialized) {
    return (
      <div className="app-boot-screen">
        <Spin size="large" tip="加载中…" />
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
};

const AppRoutes: React.FC = () => {
  const { initialize, initialized } = useAuth();

  useEffect(() => {
    void initialize();
  }, [initialize]);

  if (!initialized) {
    return (
      <div className="app-boot-screen">
        <Spin size="large" tip="正在启动 LearnPath…" />
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />

      <Route
        path="/login"
        element={
          <GuestOnly>
            <LoginPage />
          </GuestOnly>
        }
      />
      <Route
        path="/register"
        element={
          <GuestOnly>
            <RegisterPage />
          </GuestOnly>
        }
      />

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
};

const App: React.FC = () => {
  return (
    <ConfigProvider locale={zhCN} theme={theme}>
      <AntApp>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
};

export default App;
