/**
 * 学习画像雷达图
 */

import React, { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { Alert, Badge, Space, Tag, Typography } from "antd";
import type { ProfileData } from "@/types/profile";

const { Text } = Typography;

const METRIC_LABELS: Array<[keyof ProfileData, string]> = [
  ["learning_style", "学习风格"],
  ["best_time", "最佳学习时段"],
  ["learning_rhythm", "学习节奏"],
  ["feedback_baseline", "反馈基线"],
  ["persistence", "持续力"],
  ["knowledge_retention", "知识保留"],
];

interface ProfileRadarProps {
  profile: ProfileData;
}

const ProfileRadar: React.FC<ProfileRadarProps> = ({ profile }) => {
  const option = useMemo(
    () => ({
      tooltip: { trigger: "item" },
      radar: {
        radius: "65%",
        splitNumber: 5,
        axisName: {
          color: "#334155",
        },
        indicator: METRIC_LABELS.map(([key, name]) => ({
          name,
          max: 100,
          color: profile[key].confidence < 60 ? "#d97706" : "#0f766e",
        })),
      },
      series: [
        {
          type: "radar",
          data: [
            {
              value: METRIC_LABELS.map(([key]) => profile[key].confidence),
              name: "画像置信度",
              areaStyle: {
                color: "rgba(15, 118, 110, 0.2)",
              },
              lineStyle: {
                color: "#0f766e",
              },
              itemStyle: {
                color: "#0f766e",
              },
            },
          ],
        },
      ],
    }),
    [profile]
  );

  return (
    <div className="profile-radar">
      <ReactECharts option={option} style={{ height: 360 }} />
      <div className="profile-radar__list">
        {METRIC_LABELS.map(([key, label]) => {
          const metric = profile[key];
          const lowConfidence = metric.confidence < 60;
          return (
            <div key={key} className="profile-radar__item">
              <Space align="start">
                <Badge color={lowConfidence ? "#d97706" : "#0f766e"} />
                <div>
                  <Text strong>{label}</Text>
                  <div>
                    <Text type="secondary">标签：{metric.label || "暂无"}</Text>
                  </div>
                  <Space size={8} wrap style={{ marginTop: 6 }}>
                    <Tag color={lowConfidence ? "orange" : "green"}>
                      可信度：{metric.confidence}%
                    </Tag>
                    {lowConfidence && <Alert type="warning" showIcon message="待更多反馈校准" style={{ padding: "4px 10px" }} />}
                  </Space>
                </div>
              </Space>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ProfileRadar;
