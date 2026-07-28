/**
 * 学习画像页面
 */

import React, { useEffect, useMemo, useState } from "react";
import { Alert, Card, Col, Empty, Row, Timeline, Tag, Typography, message } from "antd";
import { CheckCircleOutlined } from "@ant-design/icons";
import ProfileRadar from "@/components/ProfileRadar";
import WeeklyReport from "@/components/WeeklyReport";
import { fetchProfileWithTimeline } from "@/services/profile";
import { fetchTodayTasks } from "@/services/tasks";
import type { DailyTask } from "@/types";
import type { ProfileResponse, ProfileTimelineItem } from "@/types/profile";

const { Title, Paragraph, Text } = Typography;

const ProfilePage: React.FC = () => {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [timeline, setTimeline] = useState<ProfileTimelineItem[]>([]);
  const [tasks, setTasks] = useState<DailyTask[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [{ profile, timeline }, todayTasks] = await Promise.all([
          fetchProfileWithTimeline(),
          fetchTodayTasks().catch(() => []),
        ]);
        setProfile(profile);
        setTimeline(timeline);
        setTasks(todayTasks);
      } catch (err) {
        message.error(err instanceof Error ? err.message : "加载画像失败");
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, []);

  const confidence = useMemo(() => {
    if (!profile) return 0;
    const values = Object.values(profile.profile).map((item) => item.confidence);
    return values.length > 0 ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : 0;
  }, [profile]);

  return (
    <div className="profile-page">
      <div className="page-hero">
        <div>
          <Tag color="cyan" icon={<CheckCircleOutlined />}>学习画像</Tag>
          <Title level={2} style={{ margin: "10px 0 8px" }}>个人画像概览</Title>
          <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 760 }}>
            画像会随着任务完成、反馈与校准逐步更新。这里展示你的六维学习特征、当前可信度与演变记录。
          </Paragraph>
        </div>
        <Card style={{ minWidth: 220 }}>
          <Text type="secondary">整体置信度</Text>
          <Title level={3} style={{ margin: 0 }}>{confidence}%</Title>
        </Card>
      </div>

      {profile?.needs_initial_survey && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="画像仍在初始化中"
          description={profile.initial_survey_question || "系统会根据更多学习反馈持续校准画像。"}
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Card title="六维画像雷达图" className="panel-card" loading={loading}>
            {profile ? <ProfileRadar profile={profile.profile} /> : <Empty description="暂无画像数据" />}
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="画像摘要" className="panel-card" loading={loading}>
            <div style={{ display: "grid", gap: 12 }}>
              {profile && Object.entries(profile.profile).map(([key, item]) => (
                <div key={key}>
                  <Text type="secondary">{key}</Text>
                  <div>{item.label || "暂无"}</div>
                  <Tag color={item.confidence < 60 ? "orange" : "green"}>可信度 {item.confidence}%</Tag>
                </div>
              ))}
            </div>
          </Card>
        </Col>
      </Row>

      <Card title="本周学习概览" className="panel-card" style={{ marginTop: 16 }} loading={loading}>
        <WeeklyReport tasks={tasks} />
      </Card>

      <Card title="画像时间线" className="panel-card" style={{ marginTop: 16 }} loading={loading}>
        {timeline.length === 0 ? (
          <Empty description="暂无画像历史记录" />
        ) : (
          <Timeline
            items={timeline
              .slice()
              .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
              .map((item) => ({
                children: (
                  <div>
                    <Text strong>{new Date(item.timestamp).toLocaleDateString("zh-CN")}</Text>
                    <div style={{ marginTop: 4 }}>{item.title}</div>
                    <Text type="secondary">原因：{item.reason || "暂无"}</Text>
                  </div>
                ),
              }))}
          />
        )}
      </Card>
    </div>
  );
};

export default ProfilePage;
