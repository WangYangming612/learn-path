/**
 * 应用主布局 — 侧栏导航 + 顶栏 + 内容区
 * Step 4 仅启用 Dashboard；其余导航为后续步骤占位
 */

import React, { useMemo, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Avatar,
  Dropdown,
  Layout as AntLayout,
  Menu,
  Tooltip,
  Typography,
  theme,
} from "antd";
import type { MenuProps } from "antd";
import {
  BookOutlined,
  CalendarOutlined,
  DashboardOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useAuth } from "@/hooks/useAuth";

const { Header, Sider, Content } = AntLayout;
const { Text } = Typography;

const AppLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { token: themeToken } = theme.useToken();

  const selectedKey = useMemo(() => {
    if (location.pathname.startsWith("/plans")) return "plans";
    if (location.pathname.startsWith("/daily")) return "daily";
    if (location.pathname.startsWith("/profile")) return "profile";
    return "dashboard";
  }, [location.pathname]);

  const menuItems: MenuProps["items"] = [
    {
      key: "dashboard",
      icon: <DashboardOutlined />,
      label: <Link to="/dashboard">工作台</Link>,
    },
    {
      key: "daily",
      icon: <CalendarOutlined />,
      label: (
        <Tooltip title="Step 11 开放" placement="right">
          <span className="nav-soon">今日学习</span>
        </Tooltip>
      ),
      disabled: true,
    },
    {
      key: "plans",
      icon: <BookOutlined />,
      label: (
        <Tooltip title="Step 10 开放" placement="right">
          <span className="nav-soon">学习计划</span>
        </Tooltip>
      ),
      disabled: true,
    },
    {
      key: "profile",
      icon: <UserOutlined />,
      label: (
        <Tooltip title="Step 12 开放" placement="right">
          <span className="nav-soon">学习画像</span>
        </Tooltip>
      ),
      disabled: true,
    },
  ];

  const userMenu: MenuProps["items"] = [
    {
      key: "logout",
      icon: <LogoutOutlined />,
      label: "退出登录",
      onClick: () => {
        logout();
        navigate("/login", { replace: true });
      },
    },
  ];

  const initial = (user?.username?.[0] ?? "U").toUpperCase();

  return (
    <AntLayout className="app-layout">
      <Sider
        collapsible
        collapsed={collapsed}
        trigger={null}
        width={232}
        className="app-sider"
        breakpoint="lg"
        onBreakpoint={(broken) => setCollapsed(broken)}
      >
        <Link to="/dashboard" className="app-sider__brand">
          <span className="auth-brand__mark auth-brand__mark--sm">LP</span>
          {!collapsed && <span className="app-sider__title">LearnPath</span>}
        </Link>

        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          className="app-sider__menu"
        />

        {!collapsed && (
          <div className="app-sider__foot">
            <Text type="secondary" style={{ fontSize: 12 }}>
              Step 4 · 前端骨架
            </Text>
          </div>
        )}
      </Sider>

      <AntLayout>
        <Header
          className="app-header"
          style={{ background: themeToken.colorBgContainer }}
        >
          <button
            type="button"
            className="app-header__trigger"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </button>

          <div className="app-header__right">
            <Dropdown menu={{ items: userMenu }} placement="bottomRight">
              <button type="button" className="app-header__user">
                <Avatar
                  size={36}
                  style={{
                    background: "linear-gradient(135deg, #0f766e, #115e59)",
                    fontWeight: 600,
                  }}
                >
                  {initial}
                </Avatar>
                <span className="app-header__username">{user?.username}</span>
              </button>
            </Dropdown>
          </div>
        </Header>

        <Content className="app-content">
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
};

export default AppLayout;
