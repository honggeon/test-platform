"""
路由提取器

从 GitNexus gitnexus/src/core/ingestion/pipeline-phases/routes.ts 改写

检测框架路由并创建 Route 节点 + HANDLES_ROUTE 边：
- Next.js App Router / Pages Router
- FastAPI / Flask / Django
- Express / PHP Laravel
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional, TYPE_CHECKING

from app.kg.types import (
    GraphNode, GraphRelationship,
    NODE_ROUTE, REL_HANDLES_ROUTE,
    PhaseProgress,
)

if TYPE_CHECKING:
    from app.kg.pipeline import PipelineOutput


@dataclass
class RouteEntry:
    """路由条目"""
    url: str
    file_path: str
    method: str = "GET"
    framework: str = "unknown"
    source: str = ""


# ── 框架检测器 ────────────────────────────────────────────────────────────


class NextJSRouteExtractor:
    """Next.js 路由提取（文件系统路由 + API 路由）"""

    def extract(self, file_path: str) -> Optional[RouteEntry]:
        norm = file_path.replace("\\", "/")

        # App Router: app/xxx/page.tsx → /xxx
        if "/app/" in norm:
            idx = norm.index("/app/") + 5
            rest = norm[idx:]
            # 去掉 page.tsx / layout.tsx / route.ts 等
            if any(rest.endswith(s) for s in ["page.tsx", "page.jsx", "page.ts", "page.js",
                                                "layout.tsx", "layout.jsx"]):
                route = rest.rsplit("/", 1)[0]
                route = "/" + route if route else "/"
                route = route.replace("[", "{").replace("]", "}")  # [id] → {id}
                return RouteEntry(url=route, file_path=file_path, framework="nextjs",
                                  source="nextjs-app-router")
            # API route in app: app/api/xxx/route.ts
            if "route.ts" in rest or "route.js" in rest:
                route = rest.rsplit("/", 1)[0]
                route = "/" + route if route else "/"
                return RouteEntry(url=route, file_path=file_path, framework="nextjs",
                                  method="API", source="nextjs-app-api")

        # Pages Router: pages/xxx.tsx → /xxx
        if "/pages/" in norm:
            idx = norm.index("/pages/") + 7
            rest = norm[idx:]
            if rest.endswith((".tsx", ".jsx", ".ts", ".js")):
                route = rest.rsplit(".", 1)[0]
                route = "/" + route if route else "/"
                route = route.replace("/index", "/")
                if route != "/" and route.endswith("/"):
                    route = route[:-1]
                return RouteEntry(url=route, file_path=file_path, framework="nextjs",
                                  source="nextjs-pages-router")

        return None


class FastAPIRouteExtractor:
    """FastAPI 路由提取（装饰器正则）"""

    _ROUTE_DECORATOR = re.compile(
        r'@\s*(?:app|router)\.\s*(get|post|put|delete|patch|options|head)'
        r'\s*\(\s*[\'"]([^\'"]+)[\'"]',
        re.IGNORECASE | re.MULTILINE,
    )

    def extract(self, file_path: str, source: str) -> list[RouteEntry]:
        routes = []
        for match in self._ROUTE_DECORATOR.finditer(source):
            method = match.group(1).upper()
            url = match.group(2)
            routes.append(RouteEntry(
                url=url, file_path=file_path, method=method,
                framework="fastapi", source="decorator",
            ))
        return routes


class FlaskRouteExtractor:
    """Flask 路由提取"""

    _ROUTE_DECORATOR = re.compile(
        r'@\s*(?:app|blueprint|bp)\.route\s*\(\s*[\'"]([^\'"]+)[\'"]'
        r'(?:\s*,\s*methods\s*=\s*\[([^\]]+)\])?',
        re.IGNORECASE | re.MULTILINE,
    )

    def extract(self, file_path: str, source: str) -> list[RouteEntry]:
        routes = []
        for match in self._ROUTE_DECORATOR.finditer(source):
            url = match.group(1)
            methods_str = match.group(2)
            methods = [m.strip().strip('"\'') for m in (methods_str or "GET").split(",")]
            for method in methods:
                routes.append(RouteEntry(
                    url=url, file_path=file_path, method=method.upper(),
                    framework="flask", source="decorator",
                ))
        return routes


class DjangoRouteExtractor:
    """Django 路由提取（urls.py）"""

    _PATH_PATTERN = re.compile(
        r'path\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*',
        re.MULTILINE,
    )

    def extract(self, file_path: str, source: str) -> list[RouteEntry]:
        if not file_path.endswith("urls.py"):
            return []
        routes = []
        for match in self._PATH_PATTERN.finditer(source):
            url = match.group(1)
            routes.append(RouteEntry(
                url=url, file_path=file_path, framework="django",
                source="urls.py",
            ))
        return routes


class ExpressRouteExtractor:
    """Express.js 路由提取"""

    _ROUTE_PATTERN = re.compile(
        r'(?:app|router)\.(get|post|put|delete|patch|use)\s*\(\s*[\'"`]([^\'"`]+)[\'"`]',
        re.IGNORECASE | re.MULTILINE,
    )

    def extract(self, file_path: str, source: str) -> list[RouteEntry]:
        routes = []
        for match in self._ROUTE_PATTERN.finditer(source):
            method = match.group(1).upper()
            url = match.group(2)
            routes.append(RouteEntry(
                url=url, file_path=file_path, method=method,
                framework="express", source="method-call",
            ))
        return routes


class PHPRouteExtractor:
    """PHP Laravel 路由提取"""

    _ROUTE_PATTERN = re.compile(
        r'Route::\s*(get|post|put|delete|patch|any)\s*\(\s*[\'"]([^\'"]+)[\'"]',
        re.IGNORECASE | re.MULTILINE,
    )

    def extract(self, file_path: str, source: str) -> list[RouteEntry]:
        routes = []
        for match in self._ROUTE_PATTERN.finditer(source):
            method = match.group(1).upper()
            url = match.group(2)
            routes.append(RouteEntry(
                url=url, file_path=file_path, method=method,
                framework="laravel", source="route-facade",
            ))
        return routes


# ── 统一调度 ──────────────────────────────────────────────────────────────


class RouteExtractor:
    """统一路由提取器"""

    def __init__(self):
        self._nextjs = NextJSRouteExtractor()
        self._fastapi = FastAPIRouteExtractor()
        self._flask = FlaskRouteExtractor()
        self._django = DjangoRouteExtractor()
        self._express = ExpressRouteExtractor()
        self._php = PHPRouteExtractor()

    def extract(self, file_path: str, source: str) -> list[RouteEntry]:
        ext = os.path.splitext(file_path)[1].lower()
        routes: list[RouteEntry] = []

        # Next.js: 纯文件路径模式
        r = self._nextjs.extract(file_path)
        if r:
            routes.append(r)

        # 其他框架: 需要读取源码
        if ext in (".py", ".pyi"):
            routes.extend(self._fastapi.extract(file_path, source))
            routes.extend(self._flask.extract(file_path, source))
            routes.extend(self._django.extract(file_path, source))
        elif ext in (".js", ".jsx", ".ts", ".tsx", ".mts", ".cts"):
            routes.extend(self._express.extract(file_path, source))
        elif ext == ".php":
            routes.extend(self._php.extract(file_path, source))

        return routes


# ── Pipeline Phase ────────────────────────────────────────────────────────


def routes_phase(
    output: PipelineOutput,
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
) -> None:
    """Phase: 提取 API 路由"""
    _report(on_progress, "routes", 0, "提取 API 路由...")

    extractor = RouteExtractor()
    route_registry: dict[str, RouteEntry] = {}
    total_files = len(output.scan_results)

    for idx, scan_result in enumerate(output.scan_results):
        ext = scan_result.extension
        if ext not in (".py", ".pyi", ".js", ".jsx", ".ts", ".tsx",
                       ".mts", ".cts", ".php"):
            continue

        try:
            with open(scan_result.absolute_path, "r",
                      encoding="utf-8", errors="replace") as f:
                source = f.read()
        except (IOError, OSError):
            continue

        routes = extractor.extract(scan_result.file_path, source)
        for r in routes:
            # 规范化 URL
            url = r.url if r.url.startswith("/") else "/" + r.url
            # 去掉末尾斜杠（除了根路径）
            if url != "/" and url.endswith("/"):
                url = url[:-1]
            # 去重：相同 URL + 相同方法保留第一个
            key = f"{r.method}:{url}"
            if key not in route_registry:
                route_registry[key] = r

        if (idx + 1) % max(1, total_files // 10) == 0:
            pct = int((idx + 1) / total_files * 100)
            _report(on_progress, "routes", pct,
                    f"路由提取: {idx + 1}/{total_files} 文件")

    # 创建 Route 节点和 HANDLES_ROUTE 边
    for url, entry in route_registry.items():
        route_node_id = f"route://{url}"
        output.graph.add_node(GraphNode(
            id=route_node_id,
            type=NODE_ROUTE,
            name=url,
            file_path=entry.file_path,
            properties={
                "method": entry.method,
                "framework": entry.framework,
                "source": entry.source,
            },
        ))

        file_node_id = f"file://{entry.file_path}"
        if output.graph.get_node(file_node_id):
            rel_id = f"handles_route:{file_node_id}->{route_node_id}"
            output.graph.add_relationship(GraphRelationship(
                id=rel_id,
                source_id=file_node_id,
                target_id=route_node_id,
                type=REL_HANDLES_ROUTE,
                properties={"framework": entry.framework},
            ))

    output.stats["routes_found"] = len(route_registry)
    _report(on_progress, "routes", 100,
            f"路由: {len(route_registry)} 条")


def _report(callback, phase, percent, message=""):
    if callback:
        callback(PhaseProgress(phase=phase, percent=percent, message=message))
