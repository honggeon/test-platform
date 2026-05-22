"""
测试报告 API 路由

提供基于 MinIO 的测试报告列表和详情查询 API
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


import io
import json
import mimetypes
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.config.minio_client import MinIOClient, MinIOError
from app.schemas.common import SuccessResponse
from app.schemas.pagination import PaginatedResponse, PaginationInfo
from app.schemas.test_report import TestReportInfo, TestReportListInfo, TestReportSummary


router = APIRouter(
    prefix="/projects/{project_identifier}/test-reports",
    tags=["测试报告"],
)


@router.get(
    "",
    response_model=PaginatedResponse[TestReportListInfo],
    summary="获取测试报告列表",
    description="获取项目所有来自 MinIO 的测试报告列表",
)
async def list_test_reports(
    project_identifier: str,
    p: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
):
    """
    从 MinIO 列出项目的测试报告。

    - **project_identifier**: 项目标识符
    - **p**: 页码
    - **page_size**: 每页数量

    MinIO 存储路径: test-reports/{project_identifier}/{timestamp}/report.json
    """
    try:
        # 列出 MinIO 中的结构化报告 + Allure 报告
        from app.config.settings import settings
        client = MinIOClient.get_client()

        report_items = []
        now = datetime.now()

        # 1. 列出结构化 JSON 报告
        json_prefix = f"test-reports/{project_identifier}/"
        try:
            json_objects = list(client.list_objects(
                bucket_name=settings.minio_bucket,
                prefix=json_prefix,
                recursive=True,
            ))
        except Exception:
            json_objects = []

        for obj in json_objects:
            object_name = obj.object_name
            if not object_name.endswith("/report.json"):
                continue
            try:
                data = MinIOClient.download_file(object_name)
                report_data = json.loads(data.decode("utf-8"))
                structured = report_data.get("structured", {})
                summary_data = structured.get("summary", {})
                summary = TestReportSummary(
                    total=summary_data.get("total", 0),
                    passed=summary_data.get("passed", 0),
                    failed=summary_data.get("failed", 0),
                    skipped=summary_data.get("skipped", 0),
                    total_duration_ms=summary_data.get("total_duration_ms", 0),
                )
                parts = object_name.split("/")
                report_id = parts[2] if len(parts) >= 3 else object_name
                generated_at = report_data.get("generated_at", "")
                presigned_url = None
                try:
                    presigned_url = MinIOClient.get_presigned_url(
                        object_name=object_name,
                        expires=timedelta(hours=1),
                    )
                except Exception:
                    pass
                report_items.append(TestReportListInfo(
                    id=report_id,
                    project_identifier=project_identifier,
                    generated_at=generated_at,
                    minio_path=object_name,
                    summary=summary,
                    presigned_url=presigned_url,
                    report_type="structured",
                ))
            except Exception:
                continue

        # 2. 列出 Allure HTML 报告
        allure_prefix = f"allure-reports/{project_identifier}/"
        try:
            allure_objects = list(client.list_objects(
                bucket_name=settings.minio_bucket,
                prefix=allure_prefix,
                recursive=True,
            ))
        except Exception:
            allure_objects = []

        allure_reports_seen = set()
        for obj in allure_objects:
            object_name = obj.object_name
            if not object_name.endswith("/report.zip"):
                continue
            parts = object_name.split("/")
            report_id = parts[2] if len(parts) >= 3 else object_name
            if report_id in allure_reports_seen:
                continue
            allure_reports_seen.add(report_id)
            # 从 zip 中读取 summary 信息
            try:
                import io, zipfile
                data = MinIOClient.download_file(object_name)
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    widget_data = None
                    for name in zf.namelist():
                        if name.endswith("widgets/summary.json"):
                            widget_data = json.loads(zf.read(name))
                            break
                total = 0
                passed = 0
                failed = 0
                skipped = 0
                if widget_data:
                    stat = widget_data.get("statistic", {})
                    total = stat.get("total", 0)
                    passed = stat.get("passed", 0)
                    failed = stat.get("failed", 0)
                    skipped = stat.get("skipped", 0)
                summary = TestReportSummary(
                    total=total,
                    passed=passed,
                    failed=failed,
                    skipped=skipped,
                    total_duration_ms=0,
                )
                presigned_url = None
                try:
                    presigned_url = MinIOClient.get_presigned_url(
                        object_name=object_name,
                        expires=timedelta(hours=1),
                    )
                except Exception:
                    pass
                # 从 obj.last_modified 获取时间
                generated_at = (obj.last_modified or now).isoformat() if hasattr(obj, 'last_modified') and obj.last_modified else now.isoformat()
                report_items.append(TestReportListInfo(
                    id=f"allure_{report_id}",
                    project_identifier=project_identifier,
                    generated_at=generated_at,
                    minio_path=object_name,
                    summary=summary,
                    presigned_url=presigned_url,
                    report_type="allure",
                ))
            except Exception:
                continue

        # 按时间倒序排序（最新的在前面）
        report_items.sort(key=lambda x: x.generated_at, reverse=True)

        # 分页
        offset = (p - 1) * page_size
        total = len(report_items)
        page_items = report_items[offset:offset + page_size]

        return PaginatedResponse(
            success=True,
            data=page_items,
            pagination=PaginationInfo(
                total=total,
                page=p,
                page_size=page_size,
                prev=f"/api/v2/projects/{project_identifier}/test-reports?p={p - 1}&page_size={page_size}" if p > 1 else None,
                next=f"/api/v2/projects/{project_identifier}/test-reports?p={p + 1}&page_size={page_size}" if offset + page_size < total else None,
            ),
        )

    except MinIOError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MinIO 操作失败: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取测试报告列表失败: {str(e)}",
        )



@router.get(
    "/{report_id}",
    response_model=SuccessResponse[TestReportInfo],
    summary="获取测试报告详情",
    description="获取单个测试报告的完整详情",
)
async def get_test_report(
    project_identifier: str,
    report_id: str,
):
    """
    获取指定的测试报告详情。

    - **project_identifier**: 项目标识符
    - **report_id**: 报告 ID (时间戳，格式: YYYYMMDD_HHMMSS)
    """
    try:
        # 构建 MinIO 对象路径
        object_name = f"test-reports/{project_identifier}/{report_id}/report.json"

        # 检查文件是否存在
        if not MinIOClient.file_exists(object_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"报告未找到: {report_id}",
            )

        # 下载报告
        data = MinIOClient.download_file(object_name)
        report_data = json.loads(data.decode("utf-8"))

        structured = report_data.get("structured", {})
        summary_data = structured.get("summary", {})
        tests_data = structured.get("tests", [])

        # 构建响应
        summary = TestReportSummary(
            total=summary_data.get("total", 0),
            passed=summary_data.get("passed", 0),
            failed=summary_data.get("failed", 0),
            skipped=summary_data.get("skipped", 0),
            total_duration_ms=summary_data.get("total_duration_ms", 0),
        )

        from app.schemas.test_report import TestReportTestInfo
        tests = [
            TestReportTestInfo(
                name=t.get("name", ""),
                project=t.get("project", "default"),
                status=t.get("status", "unknown"),
                expected_status=t.get("expected_status", "passed"),
                ok=t.get("ok", True),
                duration_ms=t.get("duration_ms", 0),
                error=t.get("error"),
                stack=t.get("stack"),
            )
            for t in tests_data
        ]

        # 获取预签名 URL
        presigned_url = None
        try:
            presigned_url = MinIOClient.get_presigned_url(
                object_name=object_name,
                expires=timedelta(hours=1),
            )
        except Exception:
            pass

        report_info = TestReportInfo(
            id=report_id,
            project_identifier=project_identifier,
            framework=report_data.get("framework", "playwright"),
            test_path=report_data.get("test_path", ""),
            exit_code=report_data.get("exit_code", -1),
            summary=summary,
            tests=tests,
            generated_at=report_data.get("generated_at", ""),
            minio_path=object_name,
            presigned_url=presigned_url,
        )

        return SuccessResponse(success=True, data=report_info)

    except HTTPException:
        raise
    except MinIOError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MinIO 操作失败: {str(e)}",
        )
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="报告文件解析失败",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取测试报告详情失败: {str(e)}",
        )



def _get_allure_zip_path(project_identifier: str, report_id: str) -> str:
    """获取 Allure 报告 zip 在 MinIO 中的路径"""
    clean_id = report_id.replace("allure_", "")
    return f"allure-reports/{project_identifier}/{clean_id}/report.zip"


@router.get(
    "/{report_id}/view",
    summary="查看 Allure 报告",
    description="查看 Allure HTML 报告",
)
async def view_allure_report_root(
    project_identifier: str,
    report_id: str,
):
    """查看 Allure 报告首页 - 直接返回含 <base> 标签的 HTML"""
    html = await _serve_allure_file_raw(project_identifier, report_id, "index.html")
    # 注入 <base> 标签，让相对路径指向 /view/ 目录
    base_url = f"./view/"
    html = html.replace("<head>", f'<head><base href="{base_url}"/>')
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


async def _serve_allure_file_raw(
    project_identifier: str,
    report_id: str,
    file_path: str,
) -> str:
    """从 MinIO zip 中读取 Allure 报告文件，返回原始内容"""
    object_name = _get_allure_zip_path(project_identifier, report_id)
    if not MinIOClient.file_exists(object_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Allure 报告未找到: {report_id}",
        )
    data = MinIOClient.download_file(object_name)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if file_path not in zf.namelist():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"文件 {file_path} 未找到",
            )
        return zf.read(file_path).decode("utf-8")


@router.get(
    "/{report_id}/view/",
    summary="查看 Allure 报告首页（带尾部斜杠）",
    description="查看 Allure HTML 报告首页",
    include_in_schema=False,
)
async def view_allure_report_root_slash(
    project_identifier: str,
    report_id: str,
):
    """查看 Allure 报告首页（/view/）- 也插入 <base> 标签"""
    html = await _serve_allure_file_raw(project_identifier, report_id, "index.html")
    base_url = f"./"
    html = html.replace("<head>", f'<head><base href="{base_url}"/>')
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@router.get(
    "/{report_id}/view/{file_path:path}",
    summary="查看 Allure 报告资源文件",
    description="查看 Allure 报告的静态资源文件（JS/CSS/数据）",
)
async def view_allure_report_file(
    project_identifier: str,
    report_id: str,
    file_path: str,
):
    """查看 Allure 报告的指定资源文件"""
    return await _serve_allure_file(project_identifier, report_id, file_path)


async def _serve_allure_file(
    project_identifier: str,
    report_id: str,
    file_path: str,
):
    """
    查看 Allure 报告的 HTML 页面或资源文件。
    
    从 MinIO 的 zip 文件中提取指定文件返回。
    file_path 为空时默认返回 index.html。
    """
    try:
        object_name = _get_allure_zip_path(project_identifier, report_id)
        if not MinIOClient.file_exists(object_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Allure 报告未找到: {report_id}",
            )

        data = MinIOClient.download_file(object_name)
        target = file_path or "index.html"

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if target not in zf.namelist():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"文件 {target} 未找到",
                )
            content = zf.read(target)

        # 推断 content type
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
        }
        import mimetypes
        suffix = Path(target).suffix.lower()
        media_type = content_types.get(suffix) or mimetypes.guess_type(target)[0] or "application/octet-stream"

        from fastapi.responses import Response
        return Response(content=content, media_type=media_type)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查看 Allure 报告失败: {str(e)}",
        )
