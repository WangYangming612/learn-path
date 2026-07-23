"""
安全模块

What: 提供密码哈希和 JWT 令牌的生成/验证工具
Why: Step 3 认证系统的核心依赖，注册/登录/鉴权均需调用此模块
How: passlib 封装 bcrypt 哈希，python-jose 封装 HS256 JWT
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ── 密码哈希 ────────────────────────────────────────────────
# What: passlib CryptContext，配置 bcrypt 作为哈希算法
# Why: bcrypt 是慢哈希算法，自带盐值，抗暴力破解
#      deprecated="auto" 确保未来算法升级时自动迁移
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def hash_password(password: str) -> str:
    """
    对明文密码进行 bcrypt 哈希

    What: 将用户注册时的明文密码转为不可逆哈希
    Why: 数据泄露时攻击者无法反向推导明文密码
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码与哈希值是否匹配

    What: 登录时比对用户输入的密码与数据库中存储的哈希
    Why: bcrypt 内部提取盐值后重新哈希进行比对，安全且高效
    """
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT ────────────────────────────────────────────────────
# What: JWT 签名算法和默认有效期
# Why: HS256 是对称签名，只需 SECRET_KEY 即可签发和验证，适合单服务部署
ALGORITHM = "HS256"
DEFAULT_EXPIRE_DAYS = 7


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    生成 JWT 访问令牌

    What: 将用户标识等数据编码为签名 JWT 字符串
    Why: 无状态认证，客户端携带 Token 即可验证身份，无需服务端 Session

    Args:
        data: 载荷数据，通常包含 {"sub": user_id}
        expires_delta: 自定义有效期，默认 7 天

    Returns:
        签名的 JWT 字符串
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=DEFAULT_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    """
    解码并验证 JWT 访问令牌

    What: 验证 Token 签名和有效期，返回载荷数据
    Why: 鉴权中间件提取 user_id，确认请求者身份

    Args:
        token: 待验证的 JWT 字符串

    Returns:
        解码后的载荷字典；签名无效或过期时返回 None
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
