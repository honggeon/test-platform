"""
LLM 诊断结果缓存层

使用内存 dict + 可选 Redis，实现按上下文 key 的缓存。
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

import hashlib
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class DiagnosisCache:
    """LLM 诊断缓存

    Key: sha256(f"{status_code}|{method}|{endpoint}|{error_message}")
    Value: {"type": str, "confidence": float, "reason": str, "timestamp": float}
    TTL: 24h (86400s)
    """

    def __init__(self, redis_client=None):
        self._memory = {}
        self._redis = redis_client
        self._ttl = 86400

    @staticmethod
    def make_key(status_code: int, method: str, endpoint: str, error_message: str) -> str:
        content = f"{status_code}|{method}|{endpoint}|{error_message}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def get(self, status_code: int, method: str, endpoint: str, error_message: str) -> Optional[dict]:
        key = self.make_key(status_code, method, endpoint, error_message)
        # 先查内存
        if key in self._memory:
            item = self._memory[key]
            if time.time() - item["timestamp"] < self._ttl:
                return item
            else:
                del self._memory[key]
        # 再查 Redis（如果有）
        if self._redis:
            try:
                raw = await self._redis.get(f"diagnosis:cache:{key}")
                if raw:
                    item = json.loads(raw)
                    if time.time() - item["timestamp"] < self._ttl:
                        # 回填内存
                        self._memory[key] = item
                        return item
                    else:
                        await self._redis.delete(f"diagnosis:cache:{key}")
            except Exception as e:
                logger.warning(f"Redis 缓存读取失败: {e}")
        return None

    async def set(self, status_code: int, method: str, endpoint: str, error_message: str, value: dict):
        key = self.make_key(status_code, method, endpoint, error_message)
        item = {**value, "timestamp": time.time()}
        self._memory[key] = item
        if self._redis:
            try:
                await self._redis.set(
                    f"diagnosis:cache:{key}",
                    json.dumps(item, ensure_ascii=False),
                    ex=self._ttl,
                )
            except Exception as e:
                logger.warning(f"Redis 缓存写入失败: {e}")
