"""
知识图谱集成工具

封装现有的 KG 工具，增加超时、重试和降级逻辑。
Agent 在需要定位失败对应的源码位置时使用此类。
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

import asyncio
import logging

from app.agents.api.tools.kg_tools import (
    kg_get_symbol_context,
    kg_impact_analysis,
    kg_search_code,
)

logger = logging.getLogger(__name__)


class KGIntegrationTools:
    """KG 集成工具（带超时、重试和降级）

    封装底层 KG 工具调用，提供统一的超时控制、自动重试和降级返回。
    当 KG 服务不可用时，返回空结果而非抛出异常，保证诊断流程不中断。
    """

    TIMEOUT = 3.0
    MAX_RETRIES = 2
    RETRY_DELAY = 0.5

    def __init__(self, project_identifier: str):
        self.project_identifier = project_identifier

    async def search_code(self, query: str, node_type: str = "", limit: int = 10) -> dict:
        """搜索代码，带超时重试

        在知识图谱中搜索与 query 匹配的代码符号。

        Args:
            query: 搜索关键词（类名、函数名、概念名）
            node_type: 过滤类型（class/function/method/variable/file，留空搜索全部）
            limit: 最大返回数

        Returns:
            {"matches": [...], "error": str | None}
            matches 为空列表表示未找到或降级
        """
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    kg_search_code.ainvoke({
                        "project_identifier": self.project_identifier,
                        "query": query,
                        "node_type": node_type,
                        "limit": limit,
                    }),
                    timeout=self.TIMEOUT,
                )
                if isinstance(result, str):
                    if "未找到" in result or "未配置" in result:
                        if attempt == self.MAX_RETRIES:
                            return {"matches": [], "error": result}
                    else:
                        return {"matches": [result], "error": None}
                else:
                    return {"matches": [str(result)], "error": None}
            except asyncio.TimeoutError:
                logger.warning(f"KG search_code 超时 (尝试 {attempt + 1}/{self.MAX_RETRIES + 1})")
            except Exception as e:
                logger.warning(f"KG search_code 异常 (尝试 {attempt + 1}/{self.MAX_RETRIES + 1}): {e}")

            if attempt < self.MAX_RETRIES:
                await asyncio.sleep(self.RETRY_DELAY)

        return {"matches": [], "error": "KG search_code 最终失败，已降级"}

    async def get_symbol_context(self, symbol_name: str) -> dict:
        """获取符号上下文，带超时重试

        查询某个代码符号（类、函数、变量）的定义位置、调用关系和源码片段。

        Args:
            symbol_name: 符号名称

        Returns:
            {"context": str, "found": bool, "error": str | None}
        """
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    kg_get_symbol_context.ainvoke({
                        "project_identifier": self.project_identifier,
                        "symbol_name": symbol_name,
                    }),
                    timeout=self.TIMEOUT,
                )
                if isinstance(result, str):
                    if "未找到" in result or "未配置" in result:
                        if attempt == self.MAX_RETRIES:
                            return {"context": "", "found": False, "error": result}
                    else:
                        return {"context": result, "found": True, "error": None}
                else:
                    return {"context": str(result), "found": True, "error": None}
            except asyncio.TimeoutError:
                logger.warning(f"KG get_symbol_context 超时 (尝试 {attempt + 1}/{self.MAX_RETRIES + 1})")
            except Exception as e:
                logger.warning(f"KG get_symbol_context 异常 (尝试 {attempt + 1}/{self.MAX_RETRIES + 1}): {e}")

            if attempt < self.MAX_RETRIES:
                await asyncio.sleep(self.RETRY_DELAY)

        return {"context": "", "found": False, "error": "KG get_symbol_context 最终失败，已降级"}

    async def impact_analysis(self, symbol_name: str, direction: str = "upstream") -> dict:
        """影响分析，带超时重试

        分析修改某代码符号的影响范围。

        Args:
            symbol_name: 要分析的符号名称
            direction: 分析方向 upstream/downstream/both

        Returns:
            {"report": str, "error": str | None}
        """
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    kg_impact_analysis.ainvoke({
                        "project_identifier": self.project_identifier,
                        "symbol_name": symbol_name,
                        "direction": direction,
                    }),
                    timeout=self.TIMEOUT,
                )
                if isinstance(result, str):
                    if "未找到" in result or "未配置" in result:
                        if attempt == self.MAX_RETRIES:
                            return {"report": "", "error": result}
                    else:
                        return {"report": result, "error": None}
                else:
                    return {"report": str(result), "error": None}
            except asyncio.TimeoutError:
                logger.warning(f"KG impact_analysis 超时 (尝试 {attempt + 1}/{self.MAX_RETRIES + 1})")
            except Exception as e:
                logger.warning(f"KG impact_analysis 异常 (尝试 {attempt + 1}/{self.MAX_RETRIES + 1}): {e}")

            if attempt < self.MAX_RETRIES:
                await asyncio.sleep(self.RETRY_DELAY)

        return {"report": "", "error": "KG impact_analysis 最终失败，已降级"}
