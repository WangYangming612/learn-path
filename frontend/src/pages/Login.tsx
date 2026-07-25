/**
 * 登录页
 */

import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Alert, Button, Form, Input, message } from "antd";
import { LockOutlined, UserOutlined } from "@ant-design/icons";
import AuthLayout from "@/components/AuthLayout";
import { useAuth } from "@/hooks/useAuth";

interface LoginFormValues {
  username: string;
  password: string;
}

const LoginPage: React.FC = () => {
  const { login, loading } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  const onFinish = async (values: LoginFormValues) => {
    setError(null);
    try {
      await login(values);
      message.success("登录成功，欢迎回来");
      const redirect = params.get("redirect") || "/dashboard";
      navigate(redirect.startsWith("/") ? redirect : "/dashboard", {
        replace: true,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "登录失败，请重试";
      setError(msg);
    }
  };

  return (
    <AuthLayout
      title="欢迎回来"
      subtitle="登录后继续你的个性化学习旅程"
      footer={
        <p>
          还没有账号？{" "}
          <Link to="/register" className="auth-link">
            立即注册
          </Link>
        </p>
      }
    >
      {error && (
        <Alert
          type="error"
          showIcon
          closable
          message={error}
          onClose={() => setError(null)}
          style={{ marginBottom: 20 }}
        />
      )}

      <Form
        name="login"
        layout="vertical"
        size="large"
        requiredMark={false}
        onFinish={onFinish}
        autoComplete="on"
        className="auth-form"
      >
        <Form.Item
          name="username"
          label="用户名"
          rules={[
            { required: true, message: "请输入用户名" },
            { min: 3, message: "用户名至少 3 个字符" },
          ]}
        >
          <Input
            prefix={<UserOutlined />}
            placeholder="请输入用户名"
            autoComplete="username"
          />
        </Form.Item>

        <Form.Item
          name="password"
          label="密码"
          rules={[
            { required: true, message: "请输入密码" },
            { min: 6, message: "密码至少 6 位" },
          ]}
        >
          <Input.Password
            prefix={<LockOutlined />}
            placeholder="请输入密码"
            autoComplete="current-password"
          />
        </Form.Item>

        <Form.Item style={{ marginBottom: 8, marginTop: 8 }}>
          <Button
            type="primary"
            htmlType="submit"
            block
            loading={loading}
            className="auth-submit"
          >
            登录
          </Button>
        </Form.Item>
      </Form>
    </AuthLayout>
  );
};

export default LoginPage;
