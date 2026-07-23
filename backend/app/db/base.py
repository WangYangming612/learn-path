"""
SQLAlchemy ORM 基类

What: 定义声明式 ORM 的根基类 Base 和通用 Mixin
Why: 所有模型统一继承 Base，确保 metadata 一致、alembic 迁移可用
How: 继承 DeclarativeBase，配置 metadata 命名规则
"""

import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    ORM 根基类

    What: 所有 ORM 模型类的公共父类
    Why: 统一管理 metadata，后续 alembic 自动迁移依赖 Base.metadata
         命名规则确保外键/索引/约束有可读名称，而非数据库自动生成的 hash
    """

    metadata_options = {
        "naming_convention": {
            "ix": "ix_%(column_0_label)s",       # 索引
            "uq": "uq_%(table_name)s_%(column_0_name)s",  # 唯一约束
            "ck": "ck_%(table_name)s_%(constraint_name)s", # 检查约束
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",  # 外键
            "pk": "pk_%(table_name)s",           # 主键
        }
    }


class TimestampMixin:
    """
    时间戳混入类

    What: 为模型提供 created_at / updated_at 两个自动时间字段
    Why: 6/7 个数据实体都需要记录创建和更新时间，Mixin 消除重复代码
    How: 各模型类多继承 Base + TimestampMixin
    """

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        comment="创建时间",
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime,
        default=None,
        onupdate=func.now(),
        comment="最后更新时间",
    )
