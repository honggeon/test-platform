"""
API 测试成果物管理工具

用于保存和查询 API 端点相关的测试成果物：
- 测试计划 (test_plan)
- 测试用例 (test_case)
- 测试脚本 (test_script)
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


import json
import io
import os
import ast
from uuid import UUID, uuid4
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment, AttachmentEntityType
from app.models.api_endpoint import APIEndpoint
from app.config.minio_client import MinIOClient
from app.config.database import async_session_factory
from app.config.settings import settings
from app.utils.test_environment_url import (
    mask_sensitive_urls,
    resolve_sensitive_urls_by_project_id,
)
from app.utils.hat_paths import (
    get_api_workspace_root,
    get_api_workspace_tests_dir,
    get_hat_key_dir,
    resolve_hat_cases_dir,
    sanitize_workspace_relative_path,
    build_canonical_case_rel_dir,
    derive_case_slug,
    resolve_canonical_case_dir,
    build_execute_path_hint,
    is_valid_hat_case_dir,
    slugify_case_name,
)
from app.utils.hat_yaml_lint import lint_hat_case_dir, lint_hat_yaml_content


def _resolve_workspace_path(file_path: str) -> Path:
    """
    解析文件路径，支持 MCP workspace 中的相对路径

    Args:
        file_path: 文件路径（可以是绝对路径或相对路径）

    Returns:
        解析后的绝对路径
    """
    path = Path(file_path)

    # 获取 API workspace 根目录
    workspace_root = get_api_workspace_root()

    # 规范化路径，防止 Linux 绝对路径在 Windows 下产生嵌套目录
    normalized = sanitize_workspace_relative_path(file_path, workspace_root)
    if normalized != file_path.strip().strip("/\\"):
        path = Path(normalized)

    # 在 Windows 上，以 / 开头的路径不是真正的绝对路径（没有盘符）
    # 应该被当作相对路径处理，避免解析到 C:\
    if os.name == 'nt':  # Windows
        # 将 / 开头的路径当作相对路径
        if file_path.startswith('/') or file_path.startswith('\\'):
            # 去掉开头的 / 或 \
            file_path = normalized.lstrip('/\\')
            path = Path(file_path)

    # 如果是绝对路径，直接返回
    if path.is_absolute():
        return path

    # 检查文件是否在当前工作目录存在
    if path.exists():
        return path.resolve()

    # 尝试在 workspace 目录中查找
    workspace_path = workspace_root / path
    if workspace_path.exists():
        return workspace_path

    # 尝试在 MCP 输出目录中查找（MCP 工具可能使用环境变量指定的目录）
    mcp_output_root = os.environ.get('API_WORKSPACE_ROOT')
    if mcp_output_root:
        mcp_path = Path(mcp_output_root) / path
        if mcp_path.exists():
            return mcp_path

    # 如果都找不到，返回 workspace 路径（让调用方处理错误）
    return workspace_root / path


def _merge_context_yaml(existing: str, patch: str) -> str:
    """Merge context.yaml: keep existing keys, append missing keys from patch."""
    if not existing.strip():
        return patch
    merged_lines = existing.rstrip().splitlines()
    for line in patch.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key = stripped.split(":", 1)[0].strip()
        if key and not any(l.strip().startswith(f"{key}:") for l in merged_lines):
            merged_lines.append(line)
    return "\n".join(merged_lines) + "\n"


def _write_hat_files_to_workspace(
    case_dir: Path,
    files: dict[str, str],
    merge_context: bool = True,
) -> list[str]:
    """Write HAT case files to workspace directory. Returns lint errors."""
    case_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, content in files.items():
        rel = sanitize_workspace_relative_path(rel_path.replace("\\", "/"))
        target = case_dir / rel
        if ".." in target.parts:
            raise ValueError(f"非法路径: {rel_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if merge_context and target.name == "context.yaml" and target.exists():
            existing = target.read_text(encoding="utf-8")
            content = _merge_context_yaml(existing, content)
        target.write_text(content, encoding="utf-8")

    return lint_hat_case_dir(case_dir)


def _build_deploy_result(
    *,
    project_identifier: str,
    slug: str,
    case_dir: Path,
    files: dict[str, str],
    endpoint_id: str | None = None,
) -> dict:
    rel_dir = build_canonical_case_rel_dir(project_identifier, slug)
    execute_parts = [
        f'execute_api_script(local_script_path="{rel_dir}",',
        'framework="hat",',
        f'project_identifier="{project_identifier}"',
    ]
    if endpoint_id:
        execute_parts.append(f',endpoint_id="{endpoint_id}"')
    execute_parts.append(")")
    return {
        "success": True,
        "case_dir": rel_dir,
        "absolute_path": str(case_dir),
        "workspace_root": str(get_api_workspace_root()),
        "execute_with": "".join(execute_parts),
        "files_written": sorted(files.keys()),
        "message": f"HAT 用例已部署到 {rel_dir}",
    }


@tool
async def deploy_hat_scenario(
    files: dict[str, str],
    project_identifier: str,
    case_slug: str,
    merge_context: bool = True,
) -> dict:
    """
    将跨文件 HAT 场景用例部署到 workspace（无需 endpoint_id）。

    场景测试（多 YAML + context.yaml）应使用本工具，而非 write_file 或直接写磁盘。
    写入路径：tests/{project_identifier}/api-tests/{case_slug}/

    Args:
        files: 相对路径 -> 文件内容（如 {"0_login.yaml": "...", "context.yaml": "..."}）
        project_identifier: 项目标识符（如 PR-1）
        case_slug: 场景目录名（如 scenario_conversation_flow）
        merge_context: context.yaml 合并模式（默认 True）
    """
    if not files:
        return {"success": False, "error": "files 不能为空"}

    project_identifier = (project_identifier or "").strip().strip("/")
    if not project_identifier:
        return {"success": False, "error": "project_identifier 不能为空"}

    slug = slugify_case_name(case_slug)
    if not slug or slug == "api_case":
        return {"success": False, "error": f"无效的 case_slug: {case_slug}"}

    lint_errors: list[str] = []
    for rel, content in files.items():
        check_structure = not rel.replace("\\", "/").endswith("context.yaml")
        lint_errors.extend(
            lint_hat_yaml_content(content, rel, check_hat_structure=check_structure)
        )
    if lint_errors:
        return {"success": False, "error": "YAML 校验失败", "lint_errors": lint_errors}

    case_dir = resolve_canonical_case_dir(project_identifier, slug)
    rel_dir = build_canonical_case_rel_dir(project_identifier, slug)

    try:
        post_lint = _write_hat_files_to_workspace(case_dir, files, merge_context=merge_context)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    if post_lint:
        return {
            "success": False,
            "error": "部署后 YAML 校验失败",
            "lint_errors": post_lint,
            "case_dir": rel_dir,
        }

    return _build_deploy_result(
        project_identifier=project_identifier,
        slug=slug,
        case_dir=case_dir,
        files=files,
    )


@tool
async def list_hat_case_dirs(
    project_identifier: str = "",
) -> dict:
    """
    列出 workspace 中已部署的 HAT 用例目录（供执行前确认路径）。

    返回 canonical 路径 tests/{project}/api-tests/{case_slug}/ 及文件统计。
    """
    tests_root = get_api_workspace_tests_dir()
    workspace_root = get_api_workspace_root()
    project_identifier = (project_identifier or "").strip().strip("/")

    search_roots: list[Path] = []
    if project_identifier:
        search_roots.append(tests_root / project_identifier / "api-tests")
    else:
        for project_dir in sorted(tests_root.iterdir()) if tests_root.exists() else []:
            api_tests = project_dir / "api-tests"
            if api_tests.is_dir():
                search_roots.append(api_tests)

    cases: list[dict] = []
    for api_tests_dir in search_roots:
        if not api_tests_dir.is_dir():
            continue
        project = api_tests_dir.parent.name
        for case_path in sorted(api_tests_dir.iterdir()):
            if not case_path.is_dir():
                continue
            if not is_valid_hat_case_dir(case_path, tests_root):
                continue
            yaml_files = sorted(p.name for p in case_path.glob("*.yaml"))
            cases.append({
                "project_identifier": project,
                "case_slug": case_path.name,
                "case_dir": build_canonical_case_rel_dir(project, case_path.name),
                "absolute_path": str(case_path.resolve()),
                "yaml_count": len(yaml_files),
                "yaml_files": yaml_files[:20],
                "has_context": (case_path / "context.yaml").exists(),
            })

    return {
        "success": True,
        "workspace_root": str(workspace_root),
        "tests_root": str(tests_root),
        "case_count": len(cases),
        "cases": cases,
        "hint": (
            "执行时使用 case_dir 字段作为 execute_api_script 的 local_script_path。"
            "禁止 write_file 写 HAT 用例，须用 deploy_hat_case 或 deploy_hat_scenario。"
        ),
    }


@tool
async def deploy_hat_case(
    endpoint_id: str,
    files: dict[str, str],
    project_identifier: str = "",
    case_slug: str = "",
    merge_context: bool = True,
) -> dict:
    """
    将 HAT 用例文件部署到 workspace canonical 目录（本地执行目录）。

    所有 HAT 多文件用例应通过此工具写入 workspace，路径格式：
    tests/{project_identifier}/api-tests/{case_slug}/

    禁止 /home/... 等 Linux 绝对路径。

    Args:
        endpoint_id: API 端点 ID
        files: 相对路径 -> 文件内容
        project_identifier: 项目标识符（如 PR-1）
        case_slug: 用例目录 slug；留空则从端点 display_name 推导
        merge_context: context.yaml 合并模式（默认 True）

    Returns:
        dict: canonical 路径与 execute_api_script 调用示例
    """
    try:
        endpoint_uuid = UUID(endpoint_id)
    except (ValueError, AttributeError):
        return {"success": False, "error": f"Invalid endpoint_id: {endpoint_id}"}

    if not files:
        return {"success": False, "error": "files 不能为空"}

    project_identifier = (project_identifier or "").strip().strip("/")
    if not project_identifier:
        return {"success": False, "error": "project_identifier 不能为空"}

    lint_errors: list[str] = []
    for rel, content in files.items():
        check_structure = not rel.replace("\\", "/").endswith("context.yaml")
        lint_errors.extend(
            lint_hat_yaml_content(content, rel, check_hat_structure=check_structure)
        )
    if lint_errors:
        return {"success": False, "error": "YAML 校验失败", "lint_errors": lint_errors}

    async with async_session_factory() as session:
        endpoint_result = await session.execute(
            select(APIEndpoint).where(APIEndpoint.id == endpoint_uuid)
        )
        endpoint = endpoint_result.scalar_one_or_none()
        if not endpoint:
            return {"success": False, "error": f"Endpoint {endpoint_id} not found"}

        slug = case_slug.strip() or derive_case_slug(
            endpoint.method, endpoint.path, endpoint.display_name
        )
        case_dir = resolve_canonical_case_dir(project_identifier, slug)
        rel_dir = build_canonical_case_rel_dir(project_identifier, slug)

        try:
            post_lint = _write_hat_files_to_workspace(case_dir, files, merge_context=merge_context)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        if post_lint:
            return {
                "success": False,
                "error": "部署后 YAML 校验失败",
                "lint_errors": post_lint,
                "case_dir": rel_dir,
            }

        return _build_deploy_result(
            project_identifier=project_identifier,
            slug=slug,
            case_dir=case_dir,
            files=files,
            endpoint_id=endpoint_id,
        )


def _validate_hat_keyword_module(keyword_name: str, module_content: str) -> Optional[str]:
    """校验 HAT key_dir 扩展模块结构，返回错误信息或 None。"""
    if not keyword_name or not keyword_name.strip():
        return "keyword_name 不能为空"
    if not module_content or not module_content.strip():
        return "module_content 不能为空"

    try:
        tree = ast.parse(module_content)
    except SyntaxError as exc:
        return f"Python 语法错误: {exc}"

    classes = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == keyword_name
    ]
    if not classes:
        return f"缺少与 keyword_name 同名的类: class {keyword_name}"

    cls = classes[0]
    method_names = {
        node.name for node in cls.body if isinstance(node, ast.FunctionDef)
    }
    if keyword_name not in method_names:
        return f"类 {keyword_name} 中缺少同名方法 def {keyword_name}(self, **kwargs)"
    if "__init__" not in method_names:
        return f"类 {keyword_name} 中缺少 def __init__(self, request)"

    if "from HAT.core.globalContext import g_context" not in module_content:
        return "必须使用: from HAT.core.globalContext import g_context"

    return None


def _resolve_hat_keyword_target(scope: str, case_dir: str) -> tuple[Optional[Path], Optional[str]]:
    """解析 deploy_hat_keyword 的目标目录。"""
    if scope == "global":
        target_dir = get_hat_key_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir, None

    if scope != "case":
        return None, f"不支持的 scope: {scope}，仅支持 global 或 case"

    if not case_dir or not case_dir.strip():
        return None, "scope=case 时必须提供 case_dir（如 tests/PR-1/api-tests/delete_api_test）"

    workspace_root = get_api_workspace_root()
    cleaned = sanitize_workspace_relative_path(case_dir, workspace_root)
    cases_dir = resolve_hat_cases_dir(
        cleaned,
        get_api_workspace_tests_dir(),
        workspace_root,
    )
    target_dir = cases_dir / "key_dir"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir, None


@tool
async def save_test_plan(
    endpoint_id: str,
    plan_path: Optional[str] = None,
    test_plan: Optional[dict] = None,
    plan_content: str | dict | None = None,
    plan_format: str = "markdown",
    project_identifier: str = ""
) -> dict:
    """
    保存 API 端点的测试计划到 MinIO

    支持三种方式提供测试计划内容：
    1. 通过 plan_path 指定测试计划文件路径（参考 hat-test-planner skill 生成）
    2. 通过 test_plan 直接提供测试计划字典（JSON 格式）
    3. 通过 plan_content 直接提供测试计划内容（Markdown 字符串 或 dict，dict 会自动转为 JSON）

    Args:
        endpoint_id: API 端点 ID
        plan_path: 测试计划文件路径，如 "./api-test-plan.md"
        test_plan: 测试计划内容（字典格式），包含：
            - test_scenarios: 测试场景列表
            - coverage: 覆盖率分析
            - priority: 优先级评估
            - estimated_time: 预估测试时间
        plan_content: 测试计划内容（Markdown 字符串 或 dict），可选。dict 会自动转为 JSON 字符串
        plan_format: 计划格式（markdown, json），默认为 markdown
        project_identifier: 项目标识符

    Returns:
        dict: 包含 attachment_id 和 file_path 的字典
    """
    # 验证 endpoint_id 是否为有效的 UUID
    try:
        endpoint_uuid = UUID(endpoint_id)
    except (ValueError, AttributeError):
        return {"error": f"Invalid endpoint_id format: {endpoint_id}. Must be a valid UUID."}

    # 规范化 project_identifier（去除首尾空白和斜杠，避免 MinIO 路径中出现双斜杠）
    project_identifier = project_identifier.strip().strip("/") if project_identifier else ""

    # 获取测试计划内容
    plan_bytes = None
    content_type = None
    file_extension = None

    if plan_path:
        # 从文件读取
        try:
            # 使用智能路径解析
            plan_file = _resolve_workspace_path(plan_path)
            if not plan_file.exists():
                return {
                    "error": f"Test plan file not found: {plan_path}",
                    "hint": f"Resolved path: {plan_file}",
                    "tried_paths": [
                        f"Current: {Path(plan_path).resolve()}",
                        f"Workspace: {Path(settings.api_workspace_root).resolve() / plan_path}",
                        f"MCP: {os.environ.get('API_WORKSPACE_ROOT', 'Not set')}"
                    ]
                }
            plan_content = plan_file.read_text(encoding='utf-8')
            plan_bytes = plan_content.encode('utf-8')

            # 根据文件扩展名确定格式
            if plan_file.suffix in ['.md', '.markdown']:
                plan_format = "markdown"
                content_type = "text/markdown"
                file_extension = "md"
            elif plan_file.suffix == '.json':
                plan_format = "json"
                content_type = "application/json"
                file_extension = "json"
            else:
                # 默认使用 markdown
                content_type = "text/markdown"
                file_extension = "md"
        except Exception as e:
            return {"error": f"Failed to read test plan file: {str(e)}"}
    elif test_plan:
        # 从字典生成 JSON
        plan_json = json.dumps(test_plan, ensure_ascii=False, indent=2)
        plan_bytes = plan_json.encode('utf-8')
        content_type = "application/json"
        file_extension = "json"
        plan_format = "json"
    elif plan_content is not None:
        # 接受 str 或 dict，dict 自动转为 JSON 字符串
        if isinstance(plan_content, dict):
            plan_content = json.dumps(plan_content, ensure_ascii=False, indent=2)
        if not isinstance(plan_content, str) or not plan_content.strip():
            return {"error": "plan_content must be a non-empty string or dict"}
        plan_bytes = plan_content.encode('utf-8')
        if plan_format == "json":
            content_type = "application/json"
            file_extension = "json"
        else:
            content_type = "text/markdown"
            file_extension = "md"
    else:
        return {"error": "Either plan_path, test_plan, or plan_content must be provided"}

    async with async_session_factory() as session:
        # 查询 endpoint
        endpoint_stmt = select(APIEndpoint).where(
            APIEndpoint.id == endpoint_uuid
        )
        endpoint_result = await session.execute(endpoint_stmt)
        endpoint = endpoint_result.scalar_one_or_none()

        if not endpoint:
            return {"error": f"Endpoint {endpoint_id} not found"}

        # 生成 MinIO 对象名称
        object_name = f"api-tests/{project_identifier}/endpoints/{endpoint_id}/test-plan.{file_extension}"

        # 上传到 MinIO
        try:
            MinIOClient.upload_bytes(
                object_name=object_name,
                data=plan_bytes,
                content_type=content_type
            )
        except Exception as e:
            return {"error": f"Failed to upload test plan to MinIO: {str(e)}"}

        # 生成文件名和描述
        file_name = f"test-plan-{endpoint.display_name}.{file_extension}"
        format_desc = "Markdown" if plan_format == "markdown" else "JSON"
        description = f"API 端点 {endpoint.display_name} 的测试计划 ({format_desc})"

        # 检查是否已存在相同的附件
        existing_stmt = select(Attachment).where(
            Attachment.object_name == object_name
        )
        existing_result = await session.execute(existing_stmt)
        existing_attachment = existing_result.scalar_one_or_none()

        if existing_attachment:
            # 更新现有附件
            existing_attachment.file_size = len(plan_bytes)
            existing_attachment.content_type = content_type
            existing_attachment.file_name = file_name
            existing_attachment.description = description
            existing_attachment.updated_at = datetime.now(timezone.utc)
            attachment = existing_attachment
        else:
            # 创建新附件记录
            attachment = Attachment(
                entity_type=AttachmentEntityType.API_TEST_PLAN,
                entity_id=endpoint_uuid,
                project_id=endpoint.project_id,
                file_name=file_name,
                file_size=len(plan_bytes),
                content_type=content_type,
                object_name=object_name,
                description=description,
                created_by="api-agent"
            )
            session.add(attachment)

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            return {"error": f"Failed to save test plan: a plan with object_name '{object_name}' may already exist (concurrent write)"}

        await session.refresh(attachment)

        return {
            "success": True,
            "attachment_id": str(attachment.id),
            "file_path": object_name,
            "format": plan_format,
            "file_extension": file_extension,
            "message": f"测试计划已保存 ({format_desc})"
        }


@tool
async def save_test_cases(
    endpoint_id: str,
    test_cases: list[dict],
    project_identifier: str
) -> dict:
    """
    保存 API 端点的测试用例到 MinIO

    Args:
        endpoint_id: API 端点 ID
        test_cases: 测试用例列表，每个用例包含：
            - name: 用例名称
            - description: 用例描述
            - steps: 测试步骤
            - expected_result: 预期结果
            - priority: 优先级
        project_identifier: 项目标识符

    Returns:
        dict: 包含 attachment_id 和 file_path 的字典
    """
    # 验证 endpoint_id 是否为有效的 UUID
    try:
        endpoint_uuid = UUID(endpoint_id)
    except (ValueError, AttributeError):
        return {"error": f"Invalid endpoint_id format: {endpoint_id}. Must be a valid UUID."}

    # 规范化 project_identifier（去除首尾空白和斜杠，避免 MinIO 路径中出现双斜杠）
    project_identifier = project_identifier.strip().strip("/") if project_identifier else ""

    async with async_session_factory() as session:
        # 查询 endpoint
        endpoint_stmt = select(APIEndpoint).where(
            APIEndpoint.id == endpoint_uuid
        )
        endpoint_result = await session.execute(endpoint_stmt)
        endpoint = endpoint_result.scalar_one_or_none()

        if not endpoint:
            return {"error": f"Endpoint {endpoint_id} not found"}

        # 序列化测试用例
        cases_json = json.dumps(test_cases, ensure_ascii=False, indent=2)
        cases_bytes = cases_json.encode('utf-8')

        # 生成 MinIO 对象名称
        object_name = f"api-tests/{project_identifier}/endpoints/{endpoint_id}/test-cases.json"

        # 上传到 MinIO
        try:
            MinIOClient.upload_bytes(
                object_name=object_name,
                data=cases_bytes,
                content_type="application/json"
            )
        except Exception as e:
            return {"error": f"Failed to upload test cases to MinIO: {str(e)}"}

        # 检查是否已存在相同的附件
        existing_stmt = select(Attachment).where(
            Attachment.object_name == object_name
        )
        existing_result = await session.execute(existing_stmt)
        existing_attachment = existing_result.scalar_one_or_none()

        if existing_attachment:
            # 更新现有附件
            existing_attachment.file_size = len(cases_bytes)
            existing_attachment.description = f"API 端点 {endpoint.display_name} 的测试用例（共 {len(test_cases)} 个）"
            existing_attachment.updated_at = datetime.now(timezone.utc)
            attachment = existing_attachment
        else:
            # 创建新附件记录
            attachment = Attachment(
                entity_type=AttachmentEntityType.API_TEST_CASE,
                entity_id=endpoint_uuid,
                project_id=endpoint.project_id,
                file_name=f"test-cases-{endpoint.display_name}.json",
                file_size=len(cases_bytes),
                content_type="application/json",
                object_name=object_name,
                description=f"API 端点 {endpoint.display_name} 的测试用例（共 {len(test_cases)} 个）",
                created_by="api-agent"
            )
            session.add(attachment)

        # 更新端点的测试用例统计
        endpoint.total_test_cases = (endpoint.total_test_cases or 0) + len(test_cases)
        endpoint.updated_at = datetime.now(timezone.utc)

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            return {"error": f"Failed to save test cases: concurrent write conflict on '{object_name}'"}

        await session.refresh(attachment)

        return {
            "success": True,
            "attachment_id": str(attachment.id),
            "file_path": object_name,
            "test_cases_count": len(test_cases),
            "message": f"已保存 {len(test_cases)} 个测试用例"
        }


@tool
async def save_test_script(
    endpoint_id: str,
    script_path: Optional[str] = None,
    script_content: Optional[str] = None,
    script_language: str = "yaml",
    script_format: str = "hat",
    project_identifier: str = ""
) -> dict:
    """
    保存 API 端点的测试脚本到 MinIO

    支持两种方式提供脚本内容：
    1. 通过 script_path 指定脚本文件路径（参考 hat-test-generator skill 生成）
    2. 通过 script_content 直接提供脚本内容

    Args:
        endpoint_id: API 端点 ID
        script_path: 脚本文件路径
        script_content: 脚本内容（代码），可选
        script_language: 脚本语言（如: yaml, python）
        script_format: 脚本格式（如: hat, playwright, pytest）
        project_identifier: 项目标识符

    Returns:
        dict: 包含 attachment_id 和 file_path 的字典
    """
    # 验证 endpoint_id 是否为有效的 UUID
    try:
        endpoint_uuid = UUID(endpoint_id)
    except (ValueError, AttributeError):
        return {"error": f"Invalid endpoint_id format: {endpoint_id}. Must be a valid UUID."}

    # 规范化 project_identifier（去除首尾空白和斜杠，避免 MinIO 路径中出现双斜杠）
    project_identifier = project_identifier.strip().strip("/") if project_identifier else ""

    # 获取脚本内容
    if script_path:
        # 从文件读取
        try:
            # 使用智能路径解析
            script_file = _resolve_workspace_path(script_path)
            if not script_file.exists():
                return {
                    "error": f"Script file not found: {script_path}",
                    "hint": f"Resolved path: {script_file}",
                    "tried_paths": [
                        f"Current: {Path(script_path).resolve()}",
                        f"Workspace: {Path(settings.api_workspace_root).resolve() / script_path}",
                        f"MCP: {os.environ.get('API_WORKSPACE_ROOT', 'Not set')}"
                    ]
                }
            script_content = script_file.read_text(encoding='utf-8')
        except Exception as e:
            return {"error": f"Failed to read script file: {str(e)}"}
    elif not script_content or not script_content.strip():
        return {"error": "Either script_path or non-empty script_content must be provided"}

    async with async_session_factory() as session:
        # 查询 endpoint
        endpoint_stmt = select(APIEndpoint).where(
            APIEndpoint.id == endpoint_uuid
        )
        endpoint_result = await session.execute(endpoint_stmt)
        endpoint = endpoint_result.scalar_one_or_none()

        if not endpoint:
            return {"error": f"Endpoint {endpoint_id} not found"}

        # 确定文件扩展名
        extension = {
            "typescript": "ts",
            "javascript": "js",
            "python": "py",
            "java": "java",
        }.get(script_language, "txt")

        # 生成 MinIO 对象名称
        object_name = f"api-tests/{project_identifier}/endpoints/{endpoint_id}/test-script.{extension}"

        # 上传到 MinIO
        script_bytes = script_content.encode('utf-8')
        try:
            MinIOClient.upload_bytes(
                object_name=object_name,
                data=script_bytes,
                content_type="text/plain"
            )
        except Exception as e:
            return {"error": f"Failed to upload test script to MinIO: {str(e)}"}

        # 检查是否已存在相同的附件
        existing_stmt = select(Attachment).where(
            Attachment.object_name == object_name
        )
        existing_result = await session.execute(existing_stmt)
        existing_attachment = existing_result.scalar_one_or_none()

        if existing_attachment:
            # 更新现有附件
            existing_attachment.file_size = len(script_bytes)
            existing_attachment.description = f"API 端点 {endpoint.display_name} 的测试脚本 ({script_format} - {script_language})"
            existing_attachment.updated_at = datetime.now(timezone.utc)
            attachment = existing_attachment
        else:
            # 创建新附件记录
            attachment = Attachment(
                entity_type=AttachmentEntityType.API_TEST_SCRIPT,
                entity_id=endpoint_uuid,
                project_id=endpoint.project_id,
                file_name=f"test-script.{extension}",
                file_size=len(script_bytes),
                content_type="text/plain",
                object_name=object_name,
                description=f"API 端点 {endpoint.display_name} 的测试脚本 ({script_format} - {script_language})",
                created_by="api-agent"
            )
            session.add(attachment)

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            return {"error": f"Failed to save test script: concurrent write conflict on '{object_name}'"}
        await session.refresh(attachment)

        response: dict = {
            "success": True,
            "attachment_id": str(attachment.id),
            "file_path": object_name,
            "language": script_language,
            "format": script_format,
            "message": "测试脚本已保存",
        }

        if script_format == "hat":
            if script_path:
                resolved = _resolve_workspace_path(script_path)
                case_dir = resolved if resolved.is_dir() else resolved.parent
                try:
                    rel_dir = case_dir.resolve().relative_to(
                        get_api_workspace_root().resolve()
                    ).as_posix()
                    response["workspace_case_dir"] = rel_dir
                    response["execute_with"] = (
                        f'execute_api_script(local_script_path="{rel_dir}", '
                        f'framework="hat", project_identifier="{project_identifier}", '
                        f'endpoint_id="{endpoint_id}")'
                    )
                    lint_errors = lint_hat_case_dir(case_dir, strict=False)
                    structure_errors = lint_hat_case_dir(case_dir, strict=True)
                    if lint_errors:
                        response["lint_warnings"] = lint_errors
                    if structure_errors:
                        response["lint_structure_warnings"] = structure_errors
                except ValueError:
                    pass
            else:
                response["hint"] = (
                    "HAT 多文件用例请使用 deploy_hat_case 部署到 "
                    f"{build_execute_path_hint(project_identifier or 'PR-1')}"
                )

        return response


@tool
async def deploy_hat_keyword(
    keyword_name: str,
    module_content: str,
    scope: str = "global",
    case_dir: str = "",
) -> dict:
    """
    部署 HAT key_dir 扩展关键字模块。

    当内置 Keywords 不支持某操作类型（如自定义签名、MQ）时，生成并部署扩展模块。
    文件名、类名、方法名必须与 YAML 中的「操作类型」完全一致。

    Args:
        keyword_name: 关键字名称（如 发送请求DELETE、生成签名）
        module_content: 完整 Python 模块内容
        scope: 部署范围 — global（backend/HAT/key_dir）或 case（用例目录/key_dir）
        case_dir: scope=case 时的用例目录相对路径（相对 workspace/api）

    Returns:
        dict: 部署结果，含 file_path
    """
    validation_error = _validate_hat_keyword_module(keyword_name, module_content)
    if validation_error:
        return {"success": False, "error": validation_error}

    target_dir, resolve_error = _resolve_hat_keyword_target(scope, case_dir)
    if resolve_error:
        return {"success": False, "error": resolve_error}

    target_file = target_dir / f"{keyword_name}.py"
    if target_file.exists():
        return {
            "success": False,
            "error": f"关键字文件已存在: {target_file}",
            "hint": "HAT 增量原则：已有扩展文件不覆盖。请换名或手动修改。",
        }

    target_file.write_text(module_content, encoding="utf-8")
    return {
        "success": True,
        "keyword_name": keyword_name,
        "scope": scope,
        "file_path": str(target_file),
        "message": f"已部署 HAT 关键字 {keyword_name} 到 {target_file}",
    }


@tool
async def get_endpoint_artifacts(
    endpoint_id: str,
    artifact_type: Optional[str] = None
) -> dict:
    """
    获取 API 端点的测试成果物列表

    Args:
        endpoint_id: API 端点 ID
        artifact_type: 成果物类型过滤（可选）:
            - API_TEST_PLAN: 测试计划
            - API_TEST_CASE: 测试用例
            - API_TEST_SCRIPT: 测试脚本

    Returns:
        dict: 成果物列表，包含类型、文件名、描述、创建时间等信息
    """
    # 验证 endpoint_id 是否为有效的 UUID
    try:
        endpoint_uuid = UUID(endpoint_id)
    except (ValueError, AttributeError) as e:
        return {"error": f"Invalid endpoint_id format: {endpoint_id}. Must be a valid UUID."}

    async with async_session_factory() as session:
        # 构建查询
        stmt = select(Attachment).where(
            Attachment.entity_id == endpoint_uuid
        )

        # 按类型过滤
        if artifact_type:
            try:
                entity_type = AttachmentEntityType[artifact_type]
                stmt = stmt.where(Attachment.entity_type == entity_type)
            except KeyError:
                return {"error": f"Invalid artifact_type: {artifact_type}"}

        # 执行查询
        result = await session.execute(stmt)
        attachments = result.scalars().all()

        # 格式化返回
        artifacts = []
        for attachment in attachments:
            artifacts.append({
                "id": str(attachment.id),
                "type": attachment.entity_type.value,
                "file_name": attachment.file_name,
                "description": attachment.description,
                "file_size": attachment.file_size,
                "content_type": attachment.content_type,
                "object_name": attachment.object_name,
                "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
            })

        return {
            "success": True,
            "endpoint_id": endpoint_id,
            "artifacts": artifacts,
            "total": len(artifacts)
        }


@tool
async def get_artifact_content(
    attachment_id: str
) -> dict:
    """
    获取附件内容

    Args:
        attachment_id: 附件 ID

    Returns:
        dict: 包含文件内容和元数据的字典
    """
    async with async_session_factory() as session:
        # 查询附件
        stmt = select(Attachment).where(
            Attachment.id == UUID(attachment_id)
        )
        result = await session.execute(stmt)
        attachment = result.scalar_one_or_none()

        if not attachment:
            return {"error": f"Attachment {attachment_id} not found"}

        # 从 MinIO 下载文件
        try:
            content_bytes = MinIOClient.download_file(attachment.object_name)
            content = content_bytes.decode('utf-8')
            sensitive_urls = await resolve_sensitive_urls_by_project_id(attachment.project_id)
            content = mask_sensitive_urls(content, sensitive_urls)

            return {
                "success": True,
                "attachment_id": str(attachment.id),
                "type": attachment.entity_type.value,
                "file_name": attachment.file_name,
                "content": content,
                "content_type": attachment.content_type,
                "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
            }
        except Exception as e:
            return {"error": f"Failed to download file: {str(e)}"}
