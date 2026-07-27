/**
 * 任务卡片 — 状态操作 + 拖拽手柄
 */

import React from "react";
import { Button, Space, Tag, Typography } from "antd";
import {
  CheckOutlined,
  ClockCircleOutlined,
  HolderOutlined,
  MessageOutlined,
  MinusCircleOutlined,
} from "@ant-design/icons";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { DailyTask, TaskStatus } from "@/types";

const { Text, Paragraph } = Typography;

const statusMeta: Record<
  TaskStatus,
  { label: string; color: string }
> = {
  pending: { label: "待完成", color: "processing" },
  completed: { label: "已完成", color: "success" },
  skipped: { label: "已跳过", color: "default" },
};

export interface TaskCardProps {
  task: DailyTask;
  dragDisabled?: boolean;
  statusUpdating?: boolean;
  onStatusChange: (taskId: string, status: TaskStatus) => void;
  onFeedback?: (task: DailyTask) => void;
}

const TaskCard: React.FC<TaskCardProps> = ({
  task,
  dragDisabled = false,
  statusUpdating = false,
  onStatusChange,
  onFeedback,
}) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: task.id,
    disabled: dragDisabled,
  });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.72 : 1,
  };

  const meta = statusMeta[task.status] ?? statusMeta.pending;
  const timeLabel =
    task.start_time && task.end_time
      ? `${task.start_time} – ${task.end_time}`
      : task.start_time
        ? task.start_time
        : "灵活时段";

  return (
    <article
      ref={setNodeRef}
      style={style}
      className={`task-card task-card--${task.status}${isDragging ? " task-card--dragging" : ""}`}
    >
      <div className="task-card__rail">
        <button
          type="button"
          className="task-card__handle"
          aria-label="拖拽排序"
          disabled={dragDisabled}
          {...attributes}
          {...listeners}
        >
          <HolderOutlined />
        </button>
        <div className="task-card__time">
          <ClockCircleOutlined />
          <span>{timeLabel}</span>
        </div>
      </div>

      <div className="task-card__body">
        <div className="task-card__head">
          <div>
            {task.plan_title && (
              <Text type="secondary" className="task-card__plan">
                {task.plan_title}
              </Text>
            )}
            <h3 className="task-card__title">{task.title}</h3>
          </div>
          <Tag color={meta.color}>{meta.label}</Tag>
        </div>

        {(task.description || task.guide_content) && (
          <Paragraph type="secondary" className="task-card__desc" ellipsis={{ rows: 2 }}>
            {task.guide_content || task.description}
          </Paragraph>
        )}

        <div className="task-card__meta">
          <Tag>{task.duration_minutes} 分钟</Tag>
        </div>

        <div className="task-card__actions">
          <Space wrap>
            {task.status === "pending" && (
              <>
                <Button
                  type="primary"
                  size="small"
                  icon={<CheckOutlined />}
                  loading={statusUpdating}
                  onClick={() => onStatusChange(task.id, "completed")}
                >
                  完成
                </Button>
                <Button
                  size="small"
                  icon={<MinusCircleOutlined />}
                  loading={statusUpdating}
                  onClick={() => onStatusChange(task.id, "skipped")}
                >
                  跳过
                </Button>
              </>
            )}
            {task.status === "completed" && onFeedback && (
              <Button
                size="small"
                icon={<MessageOutlined />}
                onClick={() => onFeedback(task)}
              >
                学习反馈
              </Button>
            )}
            {task.status !== "pending" && (
              <Button
                size="small"
                type="link"
                loading={statusUpdating}
                onClick={() => onStatusChange(task.id, "pending")}
              >
                恢复待做
              </Button>
            )}
          </Space>
        </div>
      </div>
    </article>
  );
};

export default TaskCard;
