/**
 * 注册页
 */

import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, Button, Form, Input, message } from "antd";
import { LockOutlined, MailOutlined, UserOutlined } from "@ant-design/icons";
import AuthLayout from "@/components/AuthLayout";
import { useAuth } from "@/hooks/useAuth";

interface RegisterFormValues {
  username: string;
  email: string;
  password: string;
  confirm: string;
}

const RegisterPage: React.FC = () => {
  const { register, loading } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const onFinish = async (values: RegisterFormValues) => {
    setError(null);
    try {
      await register({
        username: values.username,
        email: values.email,
        password: values.password,
      });
      message.success("注册成功，已自动登录");
      navigate("/dashboard", { replace: true });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "注册失败，请重试";
      setError(msg);
    }
  };

  return (
    <AuthLayout
      title="创建账号"
      subtitle="开启你的 AI 学习搭档，三步即可开始"
      footer={
        <p>
          已有账号？{" "}
          <Link to="/login" className="auth-link">
            去登录
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
        name="register"
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
            {
              pattern: /^[a-zA-Z0-9_]{3,50}$/,
              message: "3-50 位字母、数字或下划线",
            },
          ]}
        >
          <Input
            prefix={<UserOutlined />}
            placeholder="例如 learn_path"
            autoComplete="username"
          />
        </Form.Item>

        <Form.Item
          name="email"
          label="邮箱"
          rules={[
            { required: true, message: "请输入邮箱" },
            { type: "email", message: "请输入有效的邮箱地址" },
          ]}
        >
          <Input
            prefix={<MailOutlined />}
            placeholder="name@example.com"
            autoComplete="email"
          />
        </Form.Item>

        <Form.Item
          name="password"
          label="密码"
          rules={[
            { required: true, message: "请输入密码" },
            { min: 6, message: "密码至少 6 位" },
            { max: 32, message: "密码最多 32 位" },
          ]}
        >
          <Input.Password
            prefix={<LockOutlined />}
            placeholder="设置登录密码"
            autoComplete="new-password"
          />
        </Form.Item>

        <Form.Item
          name="confirm"
          label="确认密码"
          dependencies={["password"]}
          rules={[
            { required: true, message: "请再次输入密码" },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue("password") === value) {
                  return Promise.resolve();
                }
                return Promise.reject(new Error("两次输入的密码不一致"));
              },
            }),
          ]}
        >
          <Input.Password
            prefix={<LockOutlined />}
            placeholder="再次输入密码"
            autoComplete="new-password"
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
            注册并进入
          </Button>
        </Form.Item>
      </Form>
    </AuthLayout>
  );
};

export default RegisterPage;
