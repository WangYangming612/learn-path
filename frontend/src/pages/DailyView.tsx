/**
 * 每日视图 — 时间线任务 + 拖拽重排 + 反馈对话弹窗
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Modal,
  Progress,
  Row,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CalendarOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  type DragEndEvent,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import TaskCard from "@/components/TaskCard";
import ChatBubble from "@/components/ChatBubble";
import { useTasks } from "@/hooks/useTasks";
import { useAuth } from "@/hooks/useAuth";
import * as feedbackApi from "@/services/feedback";
import type { ChatMessage, DailyTask, FeedbackSignal, TaskStatus } from "@/types";

const { Title, Paragraph, Text } = Typography;

const SIGNAL_LABEL: Record<string, string> = {
  too_easy: "偏简单",
  normal: "节奏合适",
  stuck: "有点卡住",
  need_practice: "需要多练",
};

const DailyViewPage: React.FC = () => {
  const { user } = useAuth();
  const {
    tasks,
    date,
    loading,
    generating,
    stats,
    fetchToday,
    generate,
    updateStatus,
    reorder,
  } = useTasks();

  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackTask, setFeedbackTask] = useState<DailyTask | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [sending, setSending] = useState(false);
  const [replyDone, setReplyDone] = useState(false);
  const [lastSignal, setLastSignal] = useState<FeedbackSignal | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } })
  );

  useEffect(() => {
    void fetchToday().catch(() => message.error("加载今日任务失败"));
  }, [fetchToday]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const completionRate = useMemo(() => {
    if (stats.total === 0) return 0;
    return Math.round((stats.completed / stats.total) * 100);
  }, [stats.completed, stats.total]);

  const sortableIds = useMemo(() => tasks.map((t) => t.id), [tasks]);

  const handleStatusChange = async (taskId: string, status: TaskStatus) => {
    try {
      setUpdatingId(taskId);
      const updated = await updateStatus(taskId, status);
      if (status === "completed") {
        message.success("已标记完成");
        openFeedback(updated);
      } else if (status === "skipped") {
        message.info("已跳过该任务");
      } else {
        message.success("已恢复为待完成");
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : "更新任务状态失败");
    } finally {
      setUpdatingId(null);
    }
  };

  const resetFeedbackState = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    setSessionId(null);
    setStreaming(false);
    setSending(false);
    setReplyDone(false);
    setLastSignal(null);
  };

  const closeFeedback = () => {
    resetFeedbackState();
    setFeedbackOpen(false);
    setFeedbackTask(null);
  };

  const startStream = useCallback(async (task: DailyTask) => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    setSessionId(null);
    setSending(false);
    setReplyDone(false);
    setLastSignal(null);
    setStreaming(true);

    const assistantId = `assistant-${Date.now()}`;
    setMessages([
      {
        id: assistantId,
        role: "assistant",
        content: "",
        streaming: true,
      },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const sid = await feedbackApi.startFeedbackStream(
        task.id,
        (event) => {
          if (event.type === "question_chunk") {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId
                  ? {
                      ...msg,
                      content: `${msg.content}${event.content}`,
                      streaming: true,
                    }
                  : msg
              )
            );
          } else if (event.type === "error") {
            message.error(event.content || "追问生成失败");
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId
                  ? {
                      ...msg,
                      content: event.content || "追问生成失败，请稍后再试",
                      streaming: false,
                    }
                  : msg
              )
            );
          } else if (event.type === "question_done") {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId ? { ...msg, streaming: false } : msg
              )
            );
          }
        },
        controller.signal
      );
      setSessionId(sid);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      message.error(err instanceof Error ? err.message : "启动反馈失败");
      setMessages([
        {
          id: `err-${Date.now()}`,
          role: "system",
          content: err instanceof Error ? err.message : "启动反馈失败",
        },
      ]);
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, []);

  const openFeedback = (task: DailyTask) => {
    setFeedbackTask(task);
    setFeedbackOpen(true);
    void startStream(task);
  };

  const handleSendReply = async (text: string) => {
    if (!sessionId || !feedbackTask) {
      message.warning("反馈会话尚未就绪");
      return;
    }

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
    };
    setMessages((prev) => [...prev, userMsg]);
    setSending(true);

    try {
      const result = await feedbackApi.replyFeedback({
        session_id: sessionId,
        reply: text,
      });

      setLastSignal(result.signal);
      setReplyDone(true);
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-reply-${Date.now()}`,
          role: "assistant",
          content: result.system_response,
        },
      ]);

      if (result.replan_triggered) {
        message.info("已根据反馈触发路径调整");
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : "提交回复失败");
    } finally {
      setSending(false);
    }
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = tasks.findIndex((t) => t.id === active.id);
    const newIndex = tasks.findIndex((t) => t.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;

    const next = arrayMove(tasks, oldIndex, newIndex);
    reorder(next.map((t) => t.id));
    message.success("顺序已保存到本地");
  };

  const handleGenerate = async () => {
    try {
      await generate(user?.daily_available_minutes);
      message.success("今日排期已生成");
    } catch (err) {
      message.error(err instanceof Error ? err.message : "生成排期失败");
    }
  };

  const dateLabel = useMemo(() => {
    try {
      const d = new Date(`${date}T00:00:00`);
      return d.toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "long",
        day: "numeric",
        weekday: "short",
      });
    } catch {
      return date;
    }
  }, [date]);

  return (
    <div className="daily-page">
      <div className="page-hero">
        <div>
          <Tag className="page-hero__tag" icon={<CalendarOutlined />}>
            今日学习
          </Tag>
          <Title level={2} style={{ margin: "10px 0 8px" }}>
            每日任务
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 760 }}>
            {dateLabel} · 按建议时段完成任务，完成后可开启反馈对话，帮助系统校准你的学习路径。
          </Paragraph>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void fetchToday()}>
            刷新
          </Button>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            loading={generating}
            onClick={() => void handleGenerate()}
          >
            生成今日排期
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} className="page-stats">
        {[
          { label: "今日任务", value: stats.total },
          { label: "已完成", value: stats.completed },
          { label: "剩余时长", value: `${stats.remainingMinutes} min` },
          { label: "总时长", value: `${stats.totalMinutes} min` },
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

      <Card
        className="panel-card daily-progress"
        title="今日进度"
        extra={<Text type="secondary">{completionRate}%</Text>}
      >
        <Progress
          percent={completionRate}
          strokeColor={{ from: "#0f766e", to: "#14b8a6" }}
          showInfo={false}
        />
        <Text type="secondary">
          完成 {stats.completed} / {stats.total}
          {stats.skipped > 0 ? ` · 跳过 ${stats.skipped}` : ""}
        </Text>
      </Card>

      <Card
        className="panel-card"
        title="任务时间线"
        loading={loading}
        extra={
          <Text type="secondary">
            拖拽待办卡片可调整顺序（本地保存）
          </Text>
        }
      >
        {tasks.length === 0 && !loading ? (
          <Empty
            description="今天还没有任务，点击「生成今日排期」开始学习"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          >
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={generating}
              onClick={() => void handleGenerate()}
            >
              生成今日排期
            </Button>
          </Empty>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
              <div className="daily-timeline">
                {tasks.map((task) => (
                  <div key={task.id} className="daily-timeline__item">
                    <div className="daily-timeline__dot" data-status={task.status} />
                    <TaskCard
                      task={task}
                      statusUpdating={updatingId === task.id}
                      onStatusChange={handleStatusChange}
                      onFeedback={openFeedback}
                    />
                  </div>
                ))}
              </div>
            </SortableContext>
          </DndContext>
        )}
      </Card>

      <Modal
        open={feedbackOpen}
        onCancel={closeFeedback}
        footer={null}
        width={640}
        destroyOnClose
        title={
          <Space direction="vertical" size={0}>
            <Text strong>学习反馈</Text>
            <Text type="secondary" style={{ fontWeight: 400, fontSize: 13 }}>
              {feedbackTask?.title}
            </Text>
          </Space>
        }
        className="feedback-modal"
      >
        {lastSignal && (
          <Alert
            type="success"
            showIcon
            style={{ marginBottom: 12 }}
            message={`反馈信号：${SIGNAL_LABEL[lastSignal] ?? lastSignal}`}
          />
        )}

        <ChatBubble
          messages={messages}
          isStreaming={streaming}
          sending={sending}
          disabled={!sessionId || replyDone || streaming}
          hints={
            replyDone
              ? undefined
              : [
                  "这次理解起来比预期顺利",
                  "有些地方还是卡住了，需要再练练",
                  "节奏刚好，可以按计划继续",
                ]
          }
          onSend={(text) => void handleSendReply(text)}
        />

        {replyDone && (
          <div className="feedback-modal__footer">
            <Button type="primary" onClick={closeFeedback}>
              完成
            </Button>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default DailyViewPage;
