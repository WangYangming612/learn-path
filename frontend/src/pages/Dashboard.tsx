/**
 * Dashboard 工作台 — 学习概览 + 功能入口
 */

import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, Col, Row, Tag, Typography, message } from "antd";
import {
  BookOutlined,
  CalendarOutlined,
  CompassOutlined,
  RocketOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useAuth } from "@/hooks/useAuth";
import { fetchPlans } from "@/services/plans";
import { fetchTodayTasks } from "@/services/tasks";
import { fetchProfile } from "@/services/profile";
import type { DailyTask } from "@/types";

const { Title, Paragraph, Text } = Typography;

const FEATURES = [
  {
    key: "plans",
    icon: <BookOutlined />,
    title: "学习计划",
    desc: "用自然语言描述目标，AI 生成知识 DAG 与可完成性评估。",
    step: "已开放",
    tone: "teal",
    path: "/plans",
  },
  {
    key: "daily",
    icon: <CalendarOutlined />,
    title: "每日排期",
    desc: "按画像与优先级自动编排今日任务，支持拖拽微调。",
    step: "已开放",
    tone: "cyan",
    path: "/daily",
  },
  {
    key: "feedback",
    icon: <ThunderboltOutlined />,
    title: "反馈闭环",
    desc: "对话式反馈驱动路径调整，SSE 实时呈现 Agent 回应。",
    step: "已开放",
    tone: "amber",
    path: "/daily",
  },
  {
    key: "profile",
    icon: <UserOutlined />,
    title: "学习画像",
    desc: "六维雷达图刻画风格、节奏与持续力，置信度随学习生长。",
    step: "已开放",
    tone: "slate",
    path: "/profile",
  },
] as const;

const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<DailyTask[]>([]);
  const [activePlans, setActivePlans] = useState(0);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [loading, setLoading] = useState(true);

  const hour = new Date().getHours();
  const greeting =
    hour < 6 ? "夜深了" : hour < 12 ? "早上好" : hour < 18 ? "下午好" : "晚上好";

  useEffect(() => {
    const load = async () => {
      try {
        const [taskList, planList] = await Promise.all([
          fetchTodayTasks().catch(() => []),
          fetchPlans().catch(() => ({ plans: [], total_daily_budget: 0, user_daily_available: 90, remaining_daily: 0 })),
        ]);
        setTasks(taskList);
        setActivePlans(planList.plans.filter((plan) => plan.status === "active").length);
        await fetchProfile().catch(() => null);
        setProfileLoaded(true);
      } catch (err) {
        message.error(err instanceof Error ? err.message : "加载仪表盘失败");
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, []);

  const stats = useMemo(() => {
    const total = tasks.length;
    const completed = tasks.filter((task) => task.status === "completed").length;
    const completionRate = total > 0 ? Math.round((completed / total) * 100) : 0;
    return { total, completed, completionRate };
  }, [tasks]);

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
            欢迎来到 LearnPath。这里展示你的今日学习概览、当前画像状态与能力入口。
          </Paragraph>
          <div className="dash-hero__cta">
            <Button type="primary" size="large" icon={<RocketOutlined />} onClick={() => navigate("/plans?create=1")}>
              创建第一个计划
            </Button>
            <Button size="large" icon={<CalendarOutlined />} onClick={() => navigate("/daily")}>
              查看今日任务
            </Button>
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
            <span className="dash-orbit__chip dash-orbit__chip--3">Profile</span>
          </div>
        </div>
      </section>

      <section className="dash-section">
        <div className="dash-section__head">
          <Title level={4} style={{ margin: 0 }}>
            学习概览
          </Title>
          <Text type="secondary">今日任务与活跃计划的当前状态</Text>
        </div>
        <Row gutter={[16, 16]}>
          {[
            { label: "今日任务数", value: stats.total },
            { label: "已完成任务数", value: stats.completed },
            { label: "完成率", value: `${stats.completionRate}%` },
            { label: "活跃学习计划数", value: activePlans },
          ].map((item) => (
            <Col xs={12} lg={6} key={item.label}>
              <Card loading={loading}>
                <Text type="secondary">{item.label}</Text>
                <Title level={3} style={{ margin: "8px 0 0" }}>{item.value}</Title>
              </Card>
            </Col>
          ))}
        </Row>
        {!profileLoaded && (
          <Text type="secondary" style={{ display: "block", marginTop: 8 }}>
            画像数据加载失败时，Dashboard 仍可正常展示任务与计划概览。
          </Text>
        )}
      </section>

      <section className="dash-section">
        <div className="dash-section__head">
          <Title level={4} style={{ margin: 0 }}>
            能力一览
          </Title>
          <Text type="secondary">学习计划、每日任务与画像能力已开放</Text>
        </div>

        <Row gutter={[20, 20]}>
          {FEATURES.map((item) => (
            <Col xs={24} sm={12} xl={6} key={item.key}>
              <article
                className={`dash-card dash-card--${item.tone} dash-card--clickable`}
                onClick={() => navigate(item.path)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    navigate(item.path);
                  }
                }}
              >
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
          账号：{user?.email || user?.username} · 日可用时长 {user?.daily_available_minutes ?? 90} 分钟
        </Text>
      </section>
    </div>
  );
};

export default DashboardPage;
