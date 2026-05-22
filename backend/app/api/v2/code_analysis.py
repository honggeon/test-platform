"""
代码分析 REST API

提供代码搜索、符号上下文、影响分析、变更影响分析等 REST 接口。
支持按 commit_hash 查询指定版本的图谱。
"""

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbSessionDep, CurrentUserIdDep
from app.services.analyze_service import AnalyzeService
from app.schemas.common import BaseResponse, SuccessResponse
from pydantic import BaseModel, Field
from typing import Optional


# ── Schemas ────────────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    query: str = Field(..., description="搜索关键词")
    node_type: Optional[str] = Field(default=None, description="节点类型过滤")
    limit: int = Field(default=20, ge=1, le=100, description="最大结果数")
    commit_hash: Optional[str] = Field(default=None, description="指定 commit 版本（不传则取最新）")


class SearchResult(BaseModel):
    node_id: str
    name: str
    type: str
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    score: float = 0.0
    properties: Optional[dict] = None


class SearchResponse(SuccessResponse):
    data: list[SearchResult]


class SymbolContextResponse(SuccessResponse):
    data: dict


class ImpactResponse(SuccessResponse):
    data: dict


class GraphDataResponse(SuccessResponse):
    data: dict


class CommitsResponse(SuccessResponse):
    data: list[dict]


class ChangeImpactRequest(BaseModel):
    mode: str = Field(default="manual", description="模式: manual | git_diff | compare_commits")
    file_path: Optional[str] = Field(default=None, description="文件路径（manual 模式）")
    start_line: int = Field(default=0, ge=0, description="起始行号")
    end_line: int = Field(default=0, ge=0, description="结束行号")
    base_commit: Optional[str] = Field(default=None, description="基准 commit（git_diff / compare_commits 模式）")
    target_commit: Optional[str] = Field(default="HEAD", description="目标 commit（不传则取最新分析版本）")
    max_depth: int = Field(default=3, ge=1, le=10, description="影响遍历深度")


class ChangeImpactResponse(SuccessResponse):
    data: dict


class StalenessResponse(SuccessResponse):
    data: dict


class ProcessTraceResponse(SuccessResponse):
    data: dict


# ── Router ────────────────────────────────────────────────────────────────


router = APIRouter(prefix="/projects/{project_identifier}/code-analysis")


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="搜索代码",
)
async def search_code(
    project_identifier: str,
    q: str = Query(..., description="搜索关键词"),
    node_type: Optional[str] = Query(default=None, description="节点类型"),
    limit: int = Query(default=20, ge=1, le=100),
    mode: str = Query(default="hybrid", description="搜索模式: fts | bm25 | hybrid"),
    commit_hash: Optional[str] = Query(default=None, description="指定 commit 版本"),
    db: DbSessionDep = None,
    _user_id: CurrentUserIdDep = None,
) -> SearchResponse:
    """从知识图谱中搜索代码符号（支持指定 commit 版本）"""
    service = AnalyzeService(db)
    try:
        results = await service.search(project_identifier, q, node_type, limit, mode, commit_hash)
        return SearchResponse(data=[
            SearchResult(
                node_id=r.node_id,
                name=r.name,
                type=r.type,
                file_path=r.file_path,
                start_line=r.start_line,
                score=r.score,
                properties=r.properties if hasattr(r, "properties") else None,
            )
            for r in results
        ])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/context",
    response_model=SymbolContextResponse,
    summary="获取符号上下文",
)
async def get_symbol_context(
    project_identifier: str,
    symbol: str = Query(..., description="符号名称"),
    commit_hash: Optional[str] = Query(default=None, description="指定 commit 版本"),
    db: DbSessionDep = None,
    _user_id: CurrentUserIdDep = None,
) -> SymbolContextResponse:
    """获取符号的定义位置、调用关系和源码片段（支持指定 commit 版本）"""
    service = AnalyzeService(db)
    try:
        ctx = await service.get_symbol_context(project_identifier, symbol, commit_hash)
        return SymbolContextResponse(data=ctx or {"not_found": True})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/impact",
    response_model=ImpactResponse,
    summary="影响分析",
)
async def analyze_impact(
    project_identifier: str,
    symbol: str = Query(..., description="符号名称"),
    direction: str = Query(default="upstream", description="方向: upstream/downstream/both"),
    commit_hash: Optional[str] = Query(default=None, description="指定 commit 版本"),
    db: DbSessionDep = None,
    _user_id: CurrentUserIdDep = None,
) -> ImpactResponse:
    """分析修改某符号的影响范围（支持指定 commit 版本）"""
    service = AnalyzeService(db)
    try:
        report = await service.impact_analysis(project_identifier, symbol, direction, commit_hash)
        return ImpactResponse(data=report)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/graph",
    response_model=GraphDataResponse,
    summary="获取知识图谱数据",
)
async def get_graph_data(
    project_identifier: str,
    node_limit: int = Query(default=200, ge=10, le=1000),
    rel_limit: int = Query(default=500, ge=10, le=2000),
    commit_hash: Optional[str] = Query(default=None, description="指定 commit 版本"),
    db: DbSessionDep = None,
    _user_id: CurrentUserIdDep = None,
) -> GraphDataResponse:
    """获取知识图谱的节点和关系数据（用于可视化，支持指定 commit 版本）"""
    service = AnalyzeService(db)
    try:
        data = await service.get_graph_data(project_identifier, node_limit, rel_limit, commit_hash)
        return GraphDataResponse(data=data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/commits",
    response_model=CommitsResponse,
    summary="列出已分析的 commit 版本",
)
async def list_commits(
    project_identifier: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: DbSessionDep = None,
    _user_id: CurrentUserIdDep = None,
) -> CommitsResponse:
    """列出该项目已分析的所有 commit 版本（按分析时间倒序）"""
    service = AnalyzeService(db)
    try:
        commits = await service.list_commits(project_identifier, limit)
        return CommitsResponse(data=commits)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/change-impact",
    response_model=ChangeImpactResponse,
    summary="变更影响分析",
)
async def change_impact(
    project_identifier: str,
    body: ChangeImpactRequest,
    db: DbSessionDep = None,
    _user_id: CurrentUserIdDep = None,
) -> ChangeImpactResponse:
    """分析代码改动的影响范围（支持 manual / git_diff / compare_commits 三种模式）"""
    service = AnalyzeService(db)
    try:
        data = await service.change_impact_analysis(
            project_identifier,
            mode=body.mode,
            file_path=body.file_path or "",
            start_line=body.start_line,
            end_line=body.end_line,
            base_commit=body.base_commit or "",
            target_commit=body.target_commit or "HEAD",
            max_depth=body.max_depth,
        )
        return ChangeImpactResponse(data=data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/staleness",
    response_model=StalenessResponse,
    summary="检查知识图谱陈旧度",
)
async def get_staleness(
    project_identifier: str,
    db: DbSessionDep = None,
    _user_id: CurrentUserIdDep = None,
) -> StalenessResponse:
    """检查知识图谱是否相对于代码仓库已过期"""
    service = AnalyzeService(db)
    try:
        report = await service.check_staleness(project_identifier)
        return StalenessResponse(data=report)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/process-trace",
    response_model=ProcessTraceResponse,
    summary="获取执行流调用链",
)
async def get_process_trace(
    project_identifier: str,
    process_id: str = Query(..., description="执行流节点 ID"),
    commit_hash: Optional[str] = Query(default=None, description="指定 commit 版本"),
    db: DbSessionDep = None,
    _user_id: CurrentUserIdDep = None,
) -> ProcessTraceResponse:
    """获取执行流的函数调用链（从 entry_point 开始遍历 CALLS 边）"""
    service = AnalyzeService(db)
    try:
        trace = await service.get_process_trace(project_identifier, process_id, commit_hash)
        return ProcessTraceResponse(data=trace)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
