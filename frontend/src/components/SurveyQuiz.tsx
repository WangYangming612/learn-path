/**
 * 摸底选择题问答组件
 *
 * What: 12 道选择题逐题展示，用户作答后提交计算初始画像
 * Why: 替代原有的 LLM 开放式摸底问答
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Progress,
  Radio,
  RadioChangeEvent,
  Result,
  Space,
  Typography,
  message,
} from "antd";
import {
  CheckCircleFilled,
  LeftOutlined,
  RightOutlined,
} from "@ant-design/icons";
import { fetchSurveyQuestions, submitMcSurvey } from "@/services/profile";
import type { McAnswerItem, SurveyQuestion } from "@/types/profile";

const { Title, Text, Paragraph } = Typography;

interface SurveyQuizProps {
  onComplete: () => void;
}

const SurveyQuiz: React.FC<SurveyQuizProps> = ({ onComplete }) => {
  const [questions, setQuestions] = useState<SurveyQuestion[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [completed, setCompleted] = useState(false);

  // 加载题目
  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchSurveyQuestions();
        if (data.questions.length === 0) {
          // 画像已完整，无需摸底
          onComplete();
          return;
        }
        setQuestions(data.questions);
      } catch (err) {
        message.error("加载摸底题目失败");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [onComplete]);

  const currentQuestion = questions[currentIndex];
  const total = questions.length;
  const progressPercent = total > 0 ? Math.round(((currentIndex + 1) / total) * 100) : 0;
  const isLast = currentIndex === total - 1;
  const hasAnswer = currentQuestion && answers[currentQuestion.id] !== undefined;

  const handleSelect = useCallback(
    (e: RadioChangeEvent) => {
      if (!currentQuestion) return;
      setAnswers((prev) => ({ ...prev, [currentQuestion.id]: e.target.value }));
    },
    [currentQuestion]
  );

  const handleNext = useCallback(() => {
    if (currentIndex < total - 1) {
      setCurrentIndex((i) => i + 1);
    }
  }, [currentIndex, total]);

  const handlePrev = useCallback(() => {
    if (currentIndex > 0) {
      setCurrentIndex((i) => i - 1);
    }
  }, [currentIndex]);

  const handleSubmit = useCallback(async () => {
    if (Object.keys(answers).length < total) {
      message.warning("请回答所有题目后再提交");
      return;
    }
    setSubmitting(true);
    try {
      const answerList: McAnswerItem[] = Object.entries(answers).map(
        ([qid, oid]) => ({
          question_id: Number(qid),
          option_id: oid,
        })
      );
      const result = await submitMcSurvey(answerList);
      if (result.success) {
        setCompleted(true);
      } else {
        message.error("提交失败，请重试");
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  }, [answers, total]);

  // 完成后引导用户查看画像
  const handleViewProfile = useCallback(() => {
    onComplete();
  }, [onComplete]);

  // 加载中
  if (loading) {
    return (
      <Card className="panel-card" style={{ marginBottom: 16 }}>
        <div style={{ textAlign: "center", padding: "40px 0" }}>
          <Text type="secondary">加载摸底题目中...</Text>
        </div>
      </Card>
    );
  }

  // 完成状态
  if (completed) {
    return (
      <Card className="panel-card" style={{ marginBottom: 16 }}>
        <Result
          icon={<CheckCircleFilled style={{ color: "#0f766e" }} />}
          title="摸底问答完成！"
          subTitle="已根据你的回答生成初始学习画像，点击下方按钮查看。"
          extra={
            <Button type="primary" size="large" onClick={handleViewProfile}>
              查看我的画像
            </Button>
          }
        />
      </Card>
    );
  }

  // 无题目
  if (!currentQuestion) {
    return null;
  }

  return (
    <Card className="panel-card" style={{ marginBottom: 16 }}>
      {/* 进度条 */}
      <div style={{ marginBottom: 24 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginBottom: 4,
          }}
        >
          <Text type="secondary">
            第 {currentIndex + 1}/{total} 题
          </Text>
          <Text type="secondary">{progressPercent}%</Text>
        </div>
        <Progress
          percent={progressPercent}
          showInfo={false}
          strokeColor="#0f766e"
          trailColor="#e2e8f0"
        />
      </div>

      {/* 题目 */}
      <div style={{ marginBottom: 32 }}>
        <Title level={4} style={{ marginBottom: 8, fontWeight: 600 }}>
          {currentQuestion.question}
        </Title>
        <Text type="secondary" style={{ fontSize: 13 }}>
          请选择最符合你情况的一项
        </Text>
      </div>

      {/* 选项 */}
      <Radio.Group
        onChange={handleSelect}
        value={answers[currentQuestion.id] ?? null}
        style={{ width: "100%" }}
      >
        <Space direction="vertical" style={{ width: "100%" }} size={12}>
          {currentQuestion.options.map((opt) => (
            <Radio
              key={opt.option_id}
              value={opt.option_id}
              style={{
                display: "flex",
                alignItems: "center",
                padding: "12px 16px",
                border: "1px solid #e2e8f0",
                borderRadius: 8,
                width: "100%",
                transition: "all 0.2s",
                background:
                  answers[currentQuestion.id] === opt.option_id
                    ? "#f0fdfa"
                    : "#fff",
                borderColor:
                  answers[currentQuestion.id] === opt.option_id
                    ? "#0f766e"
                    : "#e2e8f0",
              }}
            >
              <Text
                strong={
                  answers[currentQuestion.id] === opt.option_id
                }
              >
                {opt.text}
              </Text>
            </Radio>
          ))}
        </Space>
      </Radio.Group>

      {/* 导航按钮 */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: 32,
        }}
      >
        <Button
          icon={<LeftOutlined />}
          onClick={handlePrev}
          disabled={currentIndex === 0}
        >
          上一题
        </Button>
        <div>
          {isLast ? (
            <Button
              type="primary"
              onClick={handleSubmit}
              loading={submitting}
              disabled={!hasAnswer}
              style={{
                background: "#0f766e",
                borderColor: "#0f766e",
              }}
            >
              提交
            </Button>
          ) : (
            <Button
              type="primary"
              onClick={handleNext}
              disabled={!hasAnswer}
              style={{
                background: "#0f766e",
                borderColor: "#0f766e",
              }}
            >
              下一题
              <RightOutlined />
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
};

export default SurveyQuiz;
