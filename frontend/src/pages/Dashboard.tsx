/**
 * Dashboard 占位页 — Step 4 欢迎与功能预览
 */

import React from "react";
import { Button, Col, Row, Tag, Typography } from "antd";
import {
  BookOutlined,
  CalendarOutlined,
  CompassOutlined,
  RocketOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useAuth } from "@/hooks/useAuth";

const { Title, Paragraph, Text } = Typography;

const FEATURES = [
  {
    key: "plans",
    icon: <BookOutlined />,
    title: "学习计划",
    desc: "用自然语言描述目标，AI 生成知识 DAG 与可完成性评估。",
    step: "Step 10",
    tone: "teal",
  },
  {
    key: "daily",
    icon: <CalendarOutlined />,
    title: "每日排期",
    desc: "按画像与优先级自动编排今日任务，支持拖拽微调。",
    step: "Step 11",
    tone: "cyan",
  },
  {
    key: "feedback",
    icon: <ThunderboltOutlined />,
    title: "反馈闭环",
    desc: "对话式反馈驱动路径调整，SSE 实时呈现 Agent 回应。",
    step: "Step 11",
    tone: "amber",
  },
  {
    key: "profile",
    icon: <UserOutlined />,
    title: "学习画像",
    desc: "六维雷达图刻画风格、节奏与持续力，置信度随学习生长。",
    step: "Step 12",
    tone: "slate",
  },
] as const;

const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  const hour = new Date().getHours();
  const greeting =
    hour < 6
      ? "夜深了"
      : hour < 12
        ? "早上好"
        : hour < 18
          ? "下午好"
          : "晚上好";

  return (
    <div className="dash">
      <section className="dash-hero">
        <div className="dash-hero__copy">
          <Tag className="dash-hero__badge" icon={<CompassOutlined />}>
            个性化学习路径
          </Tag>
          <Title level={2} className="dash-hero__title">
            {greeting}，{user?.username}
          </Title>
          <Paragraph className="dash-hero__lead">
            欢迎来到 LearnPath。前端骨架已就绪——登录鉴权、布局导航与会话恢复均已打通。
            后续步骤将在此接入计划、每日视图与画像能力。
          </Paragraph>
          <div className="dash-hero__cta">
            <Button type="primary" size="large" icon={<RocketOutlined />} disabled>
              创建第一个计划
            </Button>
            <Text type="secondary" className="dash-hero__hint">
              计划创建将在 Step 10 开放
            </Text>
          </div>
        </div>

        <div className="dash-hero__visual" aria-hidden>
          <div className="dash-orbit">
            <div className="dash-orbit__ring" />
            <div className="dash-orbit__ring dash-orbit__ring--2" />
            <div className="dash-orbit__core">
              <span>LP</span>
            </div>
            <span className="dash-orbit__chip dash-orbit__chip--1">Plan</span>
            <span className="dash-orbit__chip dash-orbit__chip--2">Schedule</span>
            <span className="dash-orbit__chip dash-orbit__chip--3">Feedback</span>
          </div>
        </div>
      </section>

      <section className="dash-section">
        <div className="dash-section__head">
          <Title level={4} style={{ margin: 0 }}>
            即将上线的能力
          </Title>
          <Text type="secondary">当前为占位预览，不影响后续页面接入</Text>
        </div>

        <Row gutter={[20, 20]}>
          {FEATURES.map((item) => (
            <Col xs={24} sm={12} xl={6} key={item.key}>
              <article className={`dash-card dash-card--${item.tone}`}>
                <div className="dash-card__icon">{item.icon}</div>
                <div className="dash-card__meta">
                  <Text className="dash-card__step">{item.step}</Text>
                  <h3>{item.title}</h3>
                  <p>{item.desc}</p>
                </div>
              </article>
            </Col>
          ))}
        </Row>
      </section>

      <section className="dash-footnote">
        <Text type="secondary">
          账号：{user?.email || user?.username} · 日可用时长{" "}
          {user?.daily_available_minutes ?? 90} 分钟
        </Text>
      </section>
    </div>
  );
};

export default DashboardPage;
