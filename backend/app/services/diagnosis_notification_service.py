"""
WebSocket 诊断推送服务

管理 WebSocket 连接，支持心跳检测、诊断进展推送、诊断完成推送及未读报告补发。
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketConnection:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.connected = True


class ConnectionManager:
    HEARTBEAT_INTERVAL = 30
    HEARTBEAT_MISS_LIMIT = 3
    REDIS_CHANNEL_PREFIX = "diagnosis:"

    def __init__(self, redis_client=None):
        self.active: dict[str, list[WebSocketConnection]] = {}
        self.redis = redis_client
        self._redis_listener_task: Optional[asyncio.Task] = None
        # 内存记录未读报告，后续可从 Redis/DB 加载
        self._unread_reports: dict[str, list[dict]] = {}

    def configure_redis(self, redis_client):
        """运行时注入 Redis 客户端并启动 Pub/Sub 监听"""
        self.redis = redis_client
        if redis_client and (self._redis_listener_task is None or self._redis_listener_task.done()):
            self._redis_listener_task = asyncio.create_task(self._redis_listener_loop())

    async def _redis_listener_loop(self):
        """订阅 diagnosis:* 频道，将消息广播到本实例 WebSocket 连接"""
        if not self.redis:
            return
        pubsub = self.redis.pubsub()
        try:
            await pubsub.psubscribe(f"{self.REDIS_CHANNEL_PREFIX}*")
            async for message in pubsub.listen():
                if message.get("type") != "pmessage":
                    continue
                channel = message.get("channel", "")
                project_id = channel.replace(self.REDIS_CHANNEL_PREFIX, "", 1)
                if not project_id:
                    continue
                try:
                    data = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
                await self._broadcast(project_id, data)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Redis Pub/Sub 监听异常: {e}")
        finally:
            try:
                await pubsub.punsubscribe(f"{self.REDIS_CHANNEL_PREFIX}*")
                await pubsub.aclose()
            except Exception:
                pass

    async def _dispatch(self, project_id: str, data: dict):
        """多实例：Redis 发布；单实例：本地广播"""
        if self.redis:
            try:
                await self.redis.publish(
                    f"{self.REDIS_CHANNEL_PREFIX}{project_id}",
                    json.dumps(data, ensure_ascii=False),
                )
                return
            except Exception as e:
                logger.warning(f"Redis Pub/Sub 推送失败，回退本地广播: {e}")
        await self._broadcast(project_id, data)

    async def connect(self, project_id: str, websocket: WebSocket):
        await websocket.accept()
        conn = WebSocketConnection(websocket)
        self.active.setdefault(project_id, []).append(conn)
        asyncio.create_task(self._heartbeat_loop(conn, project_id))
        # 连接成功后尝试补发未读报告
        asyncio.create_task(self._replay_unread(project_id, conn))

    async def _heartbeat_loop(self, conn: WebSocketConnection, project_id: str):
        miss_count = 0
        while conn.connected:
            try:
                await asyncio.wait_for(
                    conn.websocket.send_json({"type": "ping"}),
                    timeout=10
                )
                miss_count = 0
            except Exception:
                miss_count += 1
                if miss_count >= self.HEARTBEAT_MISS_LIMIT:
                    self.disconnect(project_id, conn)
                    break
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)

    def disconnect(self, project_id: str, conn: WebSocketConnection):
        conn.connected = False
        if project_id in self.active:
            try:
                self.active[project_id].remove(conn)
            except ValueError:
                pass

    async def send_progress(self, project_id: str, data: dict):
        await self._dispatch(project_id, data)

    async def _broadcast(self, project_id: str, data: dict):
        connections = self.active.get(project_id, [])
        for conn in list(connections):
            if conn.connected:
                try:
                    await conn.websocket.send_json(data)
                except Exception:
                    pass

    async def send_completed(self, project_id: str, data: dict):
        """并发发送 completed 消息 + 等待 ack，不阻塞引擎"""
        if self.redis:
            await self._dispatch(project_id, data)
            return

        connections = self.active.get(project_id, [])
        if not connections:
            await self._record_unread(project_id, data)
            return

        async def _send_and_wait(conn):
            try:
                await asyncio.wait_for(conn.websocket.send_json(data), timeout=5)
                msg = await asyncio.wait_for(conn.websocket.receive_json(), timeout=3)
                if msg.get("type") == "ack" and msg.get("report_id") == data.get("report_id"):
                    return True
            except (asyncio.TimeoutError, Exception):
                pass
            return False

        results = await asyncio.gather(*[_send_and_wait(c) for c in connections], return_exceptions=True)
        unread = [c for c, r in zip(connections, results) if not r or isinstance(r, Exception)]
        if unread:
            await self._record_unread(project_id, data)

    async def _record_unread(self, project_id: str, data: dict):
        # 简化实现：内存记录未读，后续可从 Redis/DB 加载
        self._unread_reports.setdefault(project_id, []).append(data)
        logger.info(f"记录未读报告: project={project_id}, report={data.get('report_id')}")

    async def _replay_unread(self, project_id: str, conn: WebSocketConnection):
        """向新连接补发未读报告"""
        reports = self._unread_reports.get(project_id, [])
        if not reports:
            return
        for data in list(reports):
            if not conn.connected:
                break
            try:
                await conn.websocket.send_json({**data, "type": "diagnosis_completed_replay"})
            except Exception:
                break

    async def get_unread_reports(self, project_id: str) -> list:
        return list(self._unread_reports.get(project_id, []))

    async def handle_ack(self, project_id: str, report_id: str):
        reports = self._unread_reports.get(project_id, [])
        self._unread_reports[project_id] = [r for r in reports if r.get("report_id") != report_id]


# 全局管理器实例
manager = ConnectionManager()
