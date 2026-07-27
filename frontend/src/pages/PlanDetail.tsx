/**
 * 计划详情页
 */

import React, { useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { Button, Card, Col, Modal, Row, Space, Tag, Typography, message } from "antd";
import { ArrowLeftOutlined, DeleteOutlined } from "@ant-design/icons";
import { usePlanStore } from "@/stores/planStore";
import { resolvePlanTitle } from "@/types";
import PathGraph from "@/components/PathGraph";

const { Title, Paragraph, Text } = Typography;

const PlanDetailPage: React.FC = () => {
  const { id } = useParams();
  const { currentPlan, currentGraph, fetchPlanDetail, loading, deletePlan, clearCurrentPlan } = usePlanStore();

  useEffect(() => {
    if (!id) return;
    void fetchPlanDetail(id).catch(() => message.error("加载计划详情失败"));
  }, [id, fetchPlanDetail]);

  if (!currentPlan) {
    return (
      <Card>
        <Text type="secondary">正在加载计划详情...</Text>
      </Card>
    );
  }

  const handleDelete = () => {
    Modal.confirm({
      title: `删除计划「${resolvePlanTitle(currentPlan)}」？`,
      content: "删除后将移除该计划及其本地缓存。",
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await deletePlan(currentPlan.id);
          clearCurrentPlan();
          message.success("计划已删除");
        } catch {
          message.error("删除计划失败");
        }
      },
    });
  };

  const fallbackGraph = currentGraph ?? { nodes: [], edges: [] };

  return (
    <div className="plan-detail-page">
      <Space style={{ marginBottom: 12 }}>
        <Button icon={<ArrowLeftOutlined />} type="link">
          <Link to="/plans">返回计划列表</Link>
        </Button>
        <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
          删除计划
        </Button>
      </Space>

      <Card className="panel-card plan-detail__header">
        <Row gutter={24} align="middle">
          <Col xs={24} lg={16}>
            <Tag color="cyan">知识路径</Tag>
            <Title level={2} style={{ margin: "10px 0 8px" }}>{resolvePlanTitle(currentPlan)}</Title>
            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
              {currentPlan.goal || currentPlan.description || "暂无计划说明"}
            </Paragraph>
          </Col>
          <Col xs={24} lg={8}>
            <Space wrap>
              <Tag>状态：{currentPlan.status}</Tag>
              <Tag>优先级：{currentPlan.priority}</Tag>
              <Tag>进度：{currentPlan.progress_percent}%</Tag>
              <Tag>每日预算：{currentPlan.daily_budget} min</Tag>
            </Space>
          </Col>
        </Row>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Card title="知识路径 DAG" className="panel-card" loading={loading}>
            <PathGraph data={fallbackGraph} />
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="路径摘要" className="panel-card" loading={loading}>
            <div className="plan-detail__meta">
              <div>
                <Text type="secondary">预计总时长</Text>
                <div>{currentPlan.estimated_total_hours} 小时</div>
              </div>
              <div>
                <Text type="secondary">节点总数</Text>
                <div>{currentPlan.total_nodes}</div>
              </div>
              <div>
                <Text type="secondary">已完成节点</Text>
                <div>{currentPlan.completed_nodes}</div>
              </div>
              <div>
                <Text type="secondary">可行性评估</Text>
                <div>{currentPlan.feasibility_report || "暂无"}</div>
              </div>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default PlanDetailPage;
