/**
 * 学习计划页
 */

import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CheckCircleFilled,
  ClockCircleFilled,
  PauseCircleFilled,
  PlusOutlined,
  RocketOutlined,
} from "@ant-design/icons";
import { usePlanStore } from "@/stores/planStore";
import { resolvePlanTitle, type CreatePlanRequest, type PlanPriority, type PlanSummary } from "@/types";

const { Title, Paragraph, Text } = Typography;

interface WizardValues {
  title: string;
  goal: string;
  priority: PlanPriority;
  daily_budget: number;
  duration_months: number;
  current_level: string;
  target_depth: string;
}

const priorityOptions = [
  { label: "高优先级", value: 1 },
  { label: "中优先级", value: 2 },
  { label: "低优先级", value: 3 },
];

const statusMeta: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  draft: { label: "草稿", color: "default", icon: <ClockCircleFilled /> },
  active: { label: "进行中", color: "processing", icon: <ClockCircleFilled /> },
  paused: { label: "已暂停", color: "warning", icon: <PauseCircleFilled /> },
  completed: { label: "已完成", color: "success", icon: <CheckCircleFilled /> },
};

const priorityLabelMap: Record<PlanPriority, string> = {
  1: "高",
  2: "中",
  3: "低",
};

const PlansPage: React.FC = () => {
  const { plans, loading, fetchPlans, createPlan, deletePlan } = usePlanStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const [wizardOpen, setWizardOpen] = useState(false);
  const [detailPlan, setDetailPlan] = useState<PlanSummary | null>(null);
  const [wizardStep, setWizardStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [form] = Form.useForm<WizardValues>();
  const watchedTitle = Form.useWatch("title", form);
  const watchedGoal = Form.useWatch("goal", form);
  const watchedPriority = Form.useWatch("priority", form);
  const watchedBudget = Form.useWatch("daily_budget", form);

  useEffect(() => {
    void fetchPlans().catch(() => message.error("加载计划列表失败"));
  }, [fetchPlans]);

  const openWizard = () => {
    setWizardStep(0);
    setWizardOpen(true);
    form.setFieldsValue({ priority: 2, daily_budget: 30 });
  };

  const closeWizard = () => {
    setWizardOpen(false);
    setWizardStep(0);
    form.resetFields();
    if (searchParams.has("create")) {
      const next = new URLSearchParams(searchParams);
      next.delete("create");
      setSearchParams(next, { replace: true });
    }
  };

  useEffect(() => {
    if (searchParams.get("create") === "1") {
      setWizardStep(0);
      setWizardOpen(true);
      form.setFieldsValue({ priority: 2, daily_budget: 30 });
    }
  }, [searchParams, form]);

  const stats = useMemo(() => {
    const total = plans.length;
    const active = plans.filter((item) => item.status === "active").length;
    const completed = plans.filter((item) => item.status === "completed").length;
    const daily = plans.reduce((sum, item) => sum + (Number(item.daily_budget) || 0), 0);
    return { total, active, completed, daily };
  }, [plans]);

  const handleDelete = async (record: PlanSummary) => {
    Modal.confirm({
      title: `删除计划「${resolvePlanTitle(record)}」？`,
      content: "删除后将从列表中移除，若后端删除失败也会清理本地缓存。",
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          setDeletingId(record.id);
          await deletePlan(record.id);
          message.success("计划已删除");
          if (detailPlan?.id === record.id) {
            setDetailPlan(null);
          }
        } catch {
          message.error("删除计划失败");
        } finally {
          setDeletingId((current) => (current === record.id ? null : current));
        }
      },
    });
  };

  const handleNext = async () => {
    try {
      if (wizardStep === 0) {
        await form.validateFields(["title", "daily_budget", "priority"]);
      }
      if (wizardStep === 1) {
        await form.validateFields(["goal"]);
      }
      setWizardStep((step) => Math.min(step + 1, 2));
    } catch {
      message.warning("请先补全当前步骤的信息");
    }
  };

  const handlePrev = () => setWizardStep((step) => Math.max(step - 1, 0));

  const onCreate = async () => {
    // 分步表单卸载字段时，onFinish 可能丢值；强制取全部已保存字段
    const values = form.getFieldsValue(true) as WizardValues;
    const title = String(values.title ?? "").trim();
    const goal = String(values.goal ?? "").trim();
    if (!title) {
      message.warning("请填写计划名称");
      setWizardStep(0);
      return;
    }
    if (!goal) {
      message.warning("请填写学习目标");
      setWizardStep(1);
      return;
    }

    const payload: CreatePlanRequest = {
      title,
      goal,
      priority: (values.priority ?? 2) as PlanPriority,
      daily_budget: Number(values.daily_budget) || 30,
    };
    try {
      setSubmitting(true);
      await createPlan(payload);
      message.success("计划已保存");
      closeWizard();
    } catch {
      message.error("保存计划失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="plans-page">
      <div className="page-hero">
        <div>
          <Tag className="page-hero__tag" icon={<RocketOutlined />}>
            路径管理
          </Tag>
          <Title level={2} style={{ margin: "10px 0 8px" }}>
            学习计划
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 760 }}>
            管理多条学习路径，查看进度、预算与知识图谱。创建计划后可进入详情页查看 DAG 拓扑。
          </Paragraph>
        </div>
        <Button type="primary" icon={<PlusOutlined />} size="large" onClick={openWizard}>
          创建计划
        </Button>
      </div>

      <Row gutter={[16, 16]} className="page-stats">
        {[
          { label: "计划总数", value: stats.total },
          { label: "进行中", value: stats.active },
          { label: "已完成", value: stats.completed },
          { label: "每日预算", value: `${stats.daily} min` },
        ].map((item) => (
          <Col xs={12} lg={6} key={item.label}>
            <Card className="stat-card">
              <Text type="secondary">{item.label}</Text>
              <Title level={3} style={{ margin: 0 }}>
                {item.value}
              </Title>
            </Card>
          </Col>
        ))}
      </Row>

      <Card className="panel-card" title="计划列表" extra={<Text type="secondary">点击名称查看详情</Text>}>
        <Table
          loading={loading}
          rowKey="id"
          dataSource={plans}
          pagination={false}
          columns={[
            {
              title: "计划名称",
              dataIndex: "title",
              render: (_value: string, record) => (
                <Link to={`/plans/${record.id}`}>{resolvePlanTitle(record)}</Link>
              ),
            },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: string) => {
                const meta = statusMeta[value] ?? { label: value || "未知", color: "default", icon: <ClockCircleFilled /> };
                return (
                  <Tag color={meta.color} icon={meta.icon}>
                    {meta.label}
                  </Tag>
                );
              },
            },
            {
              title: "优先级",
              dataIndex: "priority",
              render: (v: PlanPriority) => (
                <Tag color={v === 1 ? "red" : v === 2 ? "blue" : "default"}>{priorityLabelMap[v] ?? v}</Tag>
              ),
            },
            {
              title: "每日预算",
              dataIndex: "daily_budget",
              render: (v: number) => `${Number(v) || 0} min`,
            },
            {
              title: "进度",
              dataIndex: "progress_percent",
              render: (v: number) => (
                <Progress percent={Number(v) || 0} size="small" status={Number(v) >= 100 ? "success" : "active"} />
              ),
            },
            {
              title: "操作",
              render: (_, record) => (
                <Space>
                  <Button type="link" onClick={() => setDetailPlan(record)}>
                    快速预览
                  </Button>
                  <Button type="link" danger loading={deletingId === record.id} onClick={() => void handleDelete(record)}>
                    删除
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Drawer open={wizardOpen} onClose={closeWizard} width={700} title="创建学习计划" destroyOnClose>
        <Steps
          current={wizardStep}
          items={[{ title: "基础信息" }, { title: "目标解析" }, { title: "确认创建" }]}
          className="plan-wizard__steps"
        />
        <Form
          layout="vertical"
          form={form}
          onFinish={() => void onCreate()}
          initialValues={{ priority: 2, daily_budget: 30 }}
          preserve
        >
          {/* 各步骤字段始终挂载，避免分步切换后提交丢失 title/goal */}
          <div style={{ display: wizardStep === 0 ? "block" : "none" }}>
            <Form.Item name="title" label="计划名称" rules={[{ required: true, message: "请输入计划名称" }]}>
              <Input placeholder="例如：两个月掌握 React 基础" />
            </Form.Item>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="priority" label="优先级" rules={[{ required: true, message: "请选择优先级" }]}>
                  <Select options={priorityOptions} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="daily_budget" label="每日预算（分钟）" rules={[{ required: true, message: "请输入每日预算" }]}>
                  <InputNumber min={10} max={480} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
            </Row>
          </div>

          <div style={{ display: wizardStep === 1 ? "block" : "none" }}>
            <Form.Item name="goal" label="学习目标" rules={[{ required: true, message: "请输入学习目标" }]}>
              <Input.TextArea rows={5} placeholder="例如：系统掌握 React、TypeScript 和状态管理" />
            </Form.Item>
            <Row gutter={12}>
              <Col span={8}>
                <Form.Item name="duration_months" label="预计周期（月）">
                  <InputNumber min={1} max={24} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="current_level" label="当前水平">
                  <Input placeholder="入门 / 中级" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="target_depth" label="目标深度">
                  <Input placeholder="能完成项目 / 能教学" />
                </Form.Item>
              </Col>
            </Row>
          </div>

          {wizardStep === 2 && (
            <Card size="small" className="plan-preview" style={{ marginBottom: 16 }}>
              <Title level={5} style={{ marginTop: 0 }}>
                确认计划信息
              </Title>
              <Space direction="vertical" size={6}>
                <Text>计划名称：{watchedTitle || "未填写"}</Text>
                <Text>学习目标：{watchedGoal || "未填写"}</Text>
                <Text>优先级：{priorityLabelMap[(watchedPriority ?? 2) as PlanPriority]}</Text>
                <Text>每日预算：{Number(watchedBudget) || 30} min</Text>
              </Space>
            </Card>
          )}

          <Space style={{ justifyContent: "space-between", width: "100%" }}>
            <Button onClick={closeWizard}>取消</Button>
            <Space>
              <Button onClick={handlePrev} disabled={wizardStep === 0}>
                上一步
              </Button>
              {wizardStep < 2 ? (
                <Button type="primary" onClick={handleNext}>
                  下一步
                </Button>
              ) : (
                <Button type="primary" htmlType="submit" loading={submitting}>
                  创建计划
                </Button>
              )}
            </Space>
          </Space>
        </Form>
      </Drawer>

      <Modal open={Boolean(detailPlan)} onCancel={() => setDetailPlan(null)} footer={null} title="计划预览">
        {detailPlan && (
          <div className="plan-preview">
            <Title level={4} style={{ marginTop: 0 }}>
              {resolvePlanTitle(detailPlan)}
            </Title>
            <p>{detailPlan.description || detailPlan.goal || "暂无描述"}</p>
            <Space wrap>
              <Tag color={statusMeta[detailPlan.status]?.color ?? "default"}>
                状态：{statusMeta[detailPlan.status]?.label ?? detailPlan.status}
              </Tag>
              <Tag>优先级：{priorityLabelMap[detailPlan.priority]}</Tag>
              <Tag>进度：{Number(detailPlan.progress_percent) || 0}%</Tag>
            </Space>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default PlansPage;
