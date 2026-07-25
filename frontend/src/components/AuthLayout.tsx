/**
 * 认证页布局 — 左右分栏品牌 + 表单
 */

import React from "react";
import { Link } from "react-router-dom";

interface AuthLayoutProps {
  children: React.ReactNode;
  title: string;
  subtitle: string;
  footer?: React.ReactNode;
}

const AuthLayout: React.FC<AuthLayoutProps> = ({
  children,
  title,
  subtitle,
  footer,
}) => {
  return (
    <div className="auth-shell">
      <aside className="auth-brand" aria-hidden={false}>
        <div className="auth-brand__atmosphere" />
        <div className="auth-brand__grid" />
        <div className="auth-brand__orb auth-brand__orb--a" />
        <div className="auth-brand__orb auth-brand__orb--b" />

        <div className="auth-brand__content">
          <Link to="/" className="auth-brand__logo">
            <span className="auth-brand__mark">LP</span>
            <span className="auth-brand__name">LearnPath</span>
          </Link>

          <h1 className="auth-brand__headline">
            你只管学，
            <br />
            剩下的交给我。
          </h1>
          <p className="auth-brand__desc">
            多计划管理 · 每日智能排期 · 反馈驱动的动态路径调整
          </p>

          <ul className="auth-brand__features">
            <li>
              <span className="auth-brand__dot" />
              AI 拆解目标为可执行知识路径
            </li>
            <li>
              <span className="auth-brand__dot" />
              按画像智能分配每日学习时段
            </li>
            <li>
              <span className="auth-brand__dot" />
              反馈闭环，路径随你持续进化
            </li>
          </ul>
        </div>

        <div className="auth-brand__path" aria-hidden>
          <svg viewBox="0 0 420 320" fill="none">
            <path
              className="auth-path-line"
              d="M40 260 C120 240, 140 120, 220 140 S340 220, 380 80"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
            <circle className="auth-path-node" cx="40" cy="260" r="6" />
            <circle className="auth-path-node" cx="220" cy="140" r="7" />
            <circle className="auth-path-node auth-path-node--active" cx="380" cy="80" r="8" />
          </svg>
        </div>
      </aside>

      <main className="auth-panel">
        <div className="auth-panel__inner">
          <div className="auth-panel__mobile-logo">
            <span className="auth-brand__mark">LP</span>
            <span className="auth-brand__name">LearnPath</span>
          </div>
          <header className="auth-panel__header">
            <h2>{title}</h2>
            <p>{subtitle}</p>
          </header>
          {children}
          {footer ? <div className="auth-panel__footer">{footer}</div> : null}
        </div>
      </main>
    </div>
  );
};

export default AuthLayout;
