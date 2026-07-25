"""
KnowledgeNode ORM 模型

What: 知识图谱节点，表示学习计划中的原子知识单元
Why: Plan Agent 将用户目标拆解为知识树，每个节点有难度和掌握度评估
How: parent_id 外键自关联实现树形结构，remote_side 确保关系方向正确
"""

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.plan import Plan


class KnowledgeNode(Base, TimestampMixin):
    """
    知识节点表

    What: 学习路径中的单个知识点，通过 parent_id 自关联形成知识树
    Why: Plan Agent 拆解目标后输出节点列表 + 依赖关系，以此构建 DAG

    树形结构:
        根节点 (parent_id = NULL)
        ├── 子节点 A
        │   ├── 孙节点 A1
        │   └── 孙节点 A2
        └── 子节点 B
    """

    __tablename__ = "knowledge_nodes"

    # ── 主键 ────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="节点唯一标识"
    )

    # ── 外键 ────────────────────────────────────────────────
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属计划 ID",
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="SET NULL"),
        default=None,
        index=True,
        comment="父节点 ID (自关联，根节点为 NULL)",
    )

    # ── 基本信息 ────────────────────────────────────────────
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="知识点名称"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, default=None, comment="知识点描述"
    )

    # ── 学习属性 ────────────────────────────────────────────
    difficulty: Mapped[int] = mapped_column(
        Integer, default=1, comment="难度等级 (1-5)"
    )
    estimated_minutes: Mapped[int] = mapped_column(
        Integer, default=0, comment="预计学习时长（分钟）"
    )
    mastery_level: Mapped[float] = mapped_column(
        Float, default=0.0, comment="用户当前掌握程度 (0.0 ~ 1.0)"
    )

    # ── 排序 ────────────────────────────────────────────────
    order_index: Mapped[int] = mapped_column(
        Integer, default=0, comment="在同级节点中的排序序号"
    )

    # ── 关联关系 ────────────────────────────────────────────
    plan: Mapped["Plan"] = relationship(
        "Plan", back_populates="knowledge_nodes"
    )

    # ── 自关联：父节点 ──────────────────────────────────────
    # What: 当前节点的直接父节点
    # Why: remote_side 指定 FK 指向的远端列是 id，确保关系方向
    parent: Mapped[Optional["KnowledgeNode"]] = relationship(
        "KnowledgeNode",
        back_populates="children",
        remote_side="KnowledgeNode.id",
    )

    # ── 自关联：子节点 ──────────────────────────────────────
    children: Mapped[List["KnowledgeNode"]] = relationship(
        "KnowledgeNode",
        back_populates="parent",
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeNode(id={self.id}, name='{self.name}', "
            f"diff={self.difficulty}, mastery={self.mastery_level})>"
        )
