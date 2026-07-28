/**
 * 周报概览
 */

import React, { useMemo } from "react";
import { Card, Col, Row, Statistic } from "antd";
import type { DailyTask } from "@/types";

interface WeeklyReportProps {
  tasks: DailyTask[];
}

const WeeklyReport: React.FC<WeeklyReportProps> = ({ tasks }) => {
  const stats = useMemo(() => {
    const completed = tasks.filter((task) => task.status === "completed").length;
    const total = tasks.length;
    const minutes = tasks.reduce((sum, task) => sum + task.duration_minutes, 0);
    const rate = total > 0 ? Math.round((completed / total) * 100) : 0;
    return { completed, minutes, rate };
  }, [tasks]);

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} md={8}>
        <Card>
          <Statistic title="本周完成任务数" value={stats.completed} />
        </Card>
      </Col>
      <Col xs={24} md={8}>
        <Card>
          <Statistic title="学习时长" value={stats.minutes} suffix="min" />
        </Card>
      </Col>
      <Col xs={24} md={8}>
        <Card>
          <Statistic title="完成率" value={stats.rate} suffix="%" />
        </Card>
      </Col>
    </Row>
  );
};

export default WeeklyReport;
