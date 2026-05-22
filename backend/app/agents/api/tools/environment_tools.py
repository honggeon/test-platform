"""
测试环境 Agent 工具

为 AI Agent 提供测试环境查询能力，使其在生成测试脚本时使用正确的环境 URL
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


import json
from uuid import UUID

from langchain_core.tools import tool

from app.config.database import async_session_factory
from app.models.test_environment import TestEnvironment
from app.repositories.test_environment_repo import TestEnvironmentRepository


@tool
async def list_environments(
    project_identifier: str
) -> str:
    """
    获取项目下所有可用的测试环境列表

    每个环境包含：名称(name)、基础URL(base_url)、是否默认(is_default)

    Args:
        project_identifier: 项目标识符，如 "PR-1"

    Returns:
        JSON 格式的环境列表
    """
    try:
        # project_identifier 可能是如 "PR-1" 的字符串，需要查 project_id
        async with async_session_factory() as session:
            from sqlalchemy import select
            from app.models.project import Project

            project_result = await session.execute(
                select(Project).where(Project.identifier == project_identifier)
            )
            project = project_result.scalar_one_or_none()
            if not project:
                return json.dumps({
                    "success": False,
                    "error": f"项目 {project_identifier} 不存在"
                }, ensure_ascii=False, indent=2)

            repo = TestEnvironmentRepository(session)
            envs = await repo.list_by_project(project.id)

            return json.dumps({
                "success": True,
                "environments": [
                    {
                        "name": env.name,
                        "base_url": env.base_url,
                        "is_default": env.is_default,
                        "description": env.description,
                    }
                    for env in envs
                ]
            }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"查询测试环境失败: {str(e)}"
        }, ensure_ascii=False, indent=2)


@tool
async def get_default_environment(
    project_identifier: str
) -> str:
    """
    获取项目的默认测试环境

    生成的测试脚本应使用默认环境的 base_url

    Args:
        project_identifier: 项目标识符

    Returns:
        JSON 格式的默认环境信息
    """
    try:
        async with async_session_factory() as session:
            from sqlalchemy import select
            from app.models.project import Project

            project_result = await session.execute(
                select(Project).where(Project.identifier == project_identifier)
            )
            project = project_result.scalar_one_or_none()
            if not project:
                return json.dumps({
                    "success": False,
                    "error": f"项目 {project_identifier} 不存在"
                }, ensure_ascii=False, indent=2)

            repo = TestEnvironmentRepository(session)
            env = await repo.get_default(project.id)

            if not env:
                # 没有默认环境，返回项目下的第一个环境
                envs = await repo.list_by_project(project.id)
                if envs:
                    env = envs[0]

            if not env:
                return json.dumps({
                    "success": False,
                    "error": "项目尚未配置测试环境，请在项目设置中添加"
                }, ensure_ascii=False, indent=2)

            return json.dumps({
                "success": True,
                "environment": {
                    "name": env.name,
                    "base_url": env.base_url,
                    "is_default": env.is_default,
                }
            }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"获取默认测试环境失败: {str(e)}"
        }, ensure_ascii=False, indent=2)
