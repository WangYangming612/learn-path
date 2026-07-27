/**
 * 反馈对话气泡
 */

import React, { useEffect, useRef, useState } from "react";
import { Button, Input, Space, Tag, Typography } from "antd";
import { SendOutlined } from "@ant-design/icons";
import type { ChatMessage } from "@/types";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

export interface ChatBubbleProps {
  messages: ChatMessage[];
  isStreaming?: boolean;
  disabled?: boolean;
  sending?: boolean;
  hints?: string[];
  placeholder?: string;
  onSend: (text: string) => void;
}

const ChatBubble: React.FC<ChatBubbleProps> = ({
  messages,
  isStreaming = false,
  disabled = false,
  sending = false,
  hints,
  placeholder = "说说这次学习的感受…",
  onSend,
}) => {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isStreaming]);

  const submit = () => {
    const text = draft.trim();
    if (!text || disabled || sending || isStreaming) return;
    onSend(text);
    setDraft("");
  };

  return (
    <div className="chat-bubble">
      <div className="chat-bubble__list" role="log" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat-bubble__empty">
            <Text type="secondary">反馈助手正在准备追问…</Text>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`chat-bubble__row chat-bubble__row--${msg.role}`}
          >
            <div
              className={`chat-bubble__msg chat-bubble__msg--${msg.role}${
                msg.streaming ? " chat-bubble__msg--streaming" : ""
              }`}
            >
              <Paragraph className="chat-bubble__text">
                {msg.content || (msg.streaming ? "…" : "")}
              </Paragraph>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {hints && hints.length > 0 && !isStreaming && (
        <div className="chat-bubble__hints">
          <Text type="secondary" style={{ fontSize: 12 }}>
            可以这样回答：
          </Text>
          <Space wrap size={[8, 8]}>
            {hints.map((hint) => (
              <Tag
                key={hint}
                className="chat-bubble__hint"
                onClick={() => {
                  if (!disabled && !sending) setDraft(hint);
                }}
              >
                {hint}
              </Tag>
            ))}
          </Space>
        </div>
      )}

      <div className="chat-bubble__composer">
        <TextArea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={placeholder}
          autoSize={{ minRows: 2, maxRows: 4 }}
          disabled={disabled || isStreaming}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          loading={sending}
          disabled={disabled || isStreaming || !draft.trim()}
          onClick={submit}
        >
          发送
        </Button>
      </div>
    </div>
  );
};

export default ChatBubble;
