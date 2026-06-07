"""诊断 Redis 客户端工厂（可选依赖）"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def create_redis_client(redis_url: str):
    """创建 Redis 异步客户端，未安装 redis 包时返回 None"""
    if not redis_url:
        return None
    try:
        from redis.asyncio import from_url
        client = from_url(redis_url, decode_responses=True)
        await client.ping()
        logger.info("Redis 连接成功: %s", redis_url.split("@")[-1])
        return client
    except ImportError:
        logger.warning("未安装 redis 包，多实例 WS 与分布式缓存不可用")
        return None
    except Exception as e:
        logger.warning("Redis 连接失败: %s", e)
        return None


async def close_redis_client(client) -> None:
    if client is None:
        return
    try:
        await client.aclose()
    except Exception as e:
        logger.warning("关闭 Redis 连接失败: %s", e)
