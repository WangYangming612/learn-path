"""
摸底选择题相关 Pydantic Schema

What: 定义选择题问卷的请求/响应数据模型
Why: FastAPI 依赖 Pydantic 做请求体验证和响应序列化
"""

from pydantic import BaseModel, Field


class SurveyOptionSchema(BaseModel):
    """选择题选项结构（对外展示，不含 label/weight）"""
    option_id: str = Field(..., description="选项唯一标识")
    text: str = Field(..., description="选项展示文本")


class SurveyQuestionSchema(BaseModel):
    """选择题结构"""
    id: int = Field(..., description="题目编号 1-12")
    dimension: str = Field(..., description="对应画像维度")
    question: str = Field(..., description="题目文本")
    options: list[SurveyOptionSchema] = Field(..., description="选项列表")


class SurveyQuestionsResponse(BaseModel):
    """获取选择题返回"""
    questions: list[SurveyQuestionSchema] = Field(..., description="题目列表")
    total: int = Field(..., description="题目总数")


class McAnswerItem(BaseModel):
    """单条选择题答案"""
    question_id: int = Field(..., description="题目编号")
    option_id: str = Field(..., description="选中选项 ID")


class McSurveySubmitRequest(BaseModel):
    """提交选择题答案请求"""
    answers: list[McAnswerItem] = Field(
        ..., min_length=12, max_length=12, description="12 道题的作答记录"
    )


class McSurveySubmitResponse(BaseModel):
    """提交选择题答案响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field("", description="提示信息")
    profile_complete: bool = Field(True, description="画像是否完成")
    completeness: float = Field(0.0, description="画像完成度 0.0-1.0")
