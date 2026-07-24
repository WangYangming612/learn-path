
"""
反馈相关 Pydantic Schema

What: 定义 Feedback Agent 的请求/响应数据模型
Why: FastAPI 依赖 Pydantic 做请求体验证和响应序列化
"""

from pydantic import BaseModel, Field


class FeedbackStartRequest(BaseModel):
    """反馈启动请求：接收 task_id 触发追问生成"""
    task_id: str = Field(..., description="关联的每日任务 ID")


class FeedbackStartResponse(BaseModel):
    """反馈启动响应：返回 session_id 和生成的追问文本"""
    session_id: str = Field(..., description="反馈会话唯一标识")
    question: str = Field(..., description="生成的追问文本")


class FeedbackReplyRequest(BaseModel):
    """用户回复请求：接收 session_id + 用户回复文本"""
    session_id: str = Field(..., description="反馈会话唯一标识")
    reply: str = Field(..., min_length=1, description="用户对追问的回复")


class FeedbackReplyResponse(BaseModel):
    """反馈回复响应：返回信号解析和系统响应"""
    signal: str = Field(..., description="解析后的反馈信号: too_easy / normal / stuck / need_practice")
    confidence_delta: float = Field(..., description="掌握度变化量 (-1.0 ~ 1.0)")
    replan_triggered: bool = Field(..., description="是否触发重规划")
    profile_updates: dict = Field(default_factory=dict, description="待更新的画像维度")
    system_response: str = Field(..., description="系统自然语言回复")
