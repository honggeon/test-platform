# Windows 桌面应用 UI 自动化测试集成技术方案

## 1. 背景与目标

### 1.1 当前平台能力

玄鉴智能测试平台目前支持：

| 测试类型 | 被测对象 | 执行引擎 | 运行环境 |
|---------|---------|---------|---------|
| API 测试 | HTTP REST 接口 | HAT (pytest + YAML) | Linux/macOS (backend 同机) |
| Web 测试 | 浏览器页面 | Playwright (npx) | Linux/macOS (backend 同机) |
| 场景测试 | 多 API 编排 | httpx + JSONPath | Linux/macOS (backend 同机) |

### 1.2 新需求：Windows 桌面应用 UI 自动化

被测对象是 **Windows 系统上安装的 .exe 桌面应用**，测试内容是 **界面操作与验证**（点击按钮、输入文本、读取标签、截图比对等），而非底层网络通信。

### 1.3 核心挑战

```
┌─────────────────────────────────────────────────────────────────┐
│  当前平台 (Linux/macOS)                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ FastAPI  │  │ LangGraph│  │ Next.js  │                      │
│  │ :8000    │  │ :2026    │  │ :3000    │                      │
│  └──────────┘  └──────────┘  └──────────┘                      │
│                                                                  │
│  无法直接执行 →  pywinauto / WinAppDriver 必须在 Windows 上运行 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 网络通信 (HTTP/WebSocket)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Windows 执行节点 (物理机 / VM)                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Test Execution Agent (Python)                            │   │
│  │  ├─ pywinauto / WinAppDriver                              │   │
│  │  ├─ 被测 .exe 应用                                        │   │
│  │  └─ 截图 / 日志采集                                       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**关键约束**：桌面 UI 自动化必须在 Windows 上执行，而平台后端运行在 Linux/macOS 上。因此需要 **远程执行架构**。

---

## 2. 总体架构设计

### 2.1 架构图

```
┌── 平台后端 (Linux/macOS) ──────────────────────────────────────┐
│                                                                  │
│  ┌─────────────────┐   ┌──────────────────┐                     │
│  │  CSTestService  │   │  CSTestExecutor  │                     │
│  │  (CRUD + 管理)  │   │  (任务调度)       │                     │
│  └────────┬────────┘   └────────┬─────────┘                     │
│           │                     │                                │
│  ┌────────▼─────────────────────▼──────────┐                    │
│  │         CSTestAgentManager              │                    │
│  │  ┌──────────────────────────────────┐   │                    │
│  │  │ 注册管理 Windows 执行节点的连接   │   │                    │
│  │  │ 任务分发 (选择空闲节点)           │   │                    │
│  │  │ 心跳监控 (节点在线/离线)          │   │                    │
│  │  │ 结果回传 + Allure 报告生成       │   │                    │
│  │  └──────────────────────────────────┘   │                    │
│  └─────────────────────────────────────────┘                    │
│                                                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │ HTTP/WebSocket   │                  │
          ▼                  ▼                  ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Windows     │    │ Windows     │    │ Windows     │
│ 执行节点 #1  │    │ 执行节点 #2  │    │ 执行节点 #3  │
│             │    │             │    │             │
│ pywinauto   │    │ FlaUI       │    │ WinAppDriver│
│ 被测App.exe │    │ 被测App.exe │    │ 被测App.exe │
└─────────────┘    └─────────────┘    └─────────────┘
```

### 2.2 新增 vs 复用

| 层次 | 策略 | 说明 |
|------|------|------|
| 模型 (models) | **新增** `cs_test.py` | 桌面测试专属字段 |
| 仓库 (repositories) | **新增** `cs_test_repo.py` | 继承 BaseRepository |
| 服务 (services) | **新增** `cs_test_service.py` | CRUD + 任务调度 |
| 执行引擎 | **新增** `cs_test_executor.py` (调度端) + **独立** `cs_test_agent.py` (Windows 节点) | 远程执行架构 |
| HAT 关键字 | **新增** 桌面操作关键字系列 | 通过 key_dir 扩展 |
| 前端 UI | **新增** `cs-tests/` | 参考 web-tests 模式 |
| 基础设施 | **新增** Windows Agent 服务 | 独立进程，运行在 Windows 上 |

---

## 3. 数据模型设计

### 3.1 核心表

```sql
-- ============================================================
-- C/S 桌面测试用例主表
-- ============================================================
CREATE TABLE cs_tests (
    id                  UUID PRIMARY KEY,
    project_id          UUID NOT NULL REFERENCES projects(id),
    folder_id           UUID REFERENCES folders(id),
    identifier          VARCHAR(255) NOT NULL,
    name                VARCHAR(500) NOT NULL,
    description         TEXT,

    -- 应用信息
    app_name            VARCHAR(255) NOT NULL,          -- 被测应用名称
    app_path            VARCHAR(500) NOT NULL,          -- .exe 路径 (Windows 上的路径)
    app_args            VARCHAR(500),                   -- 启动参数
    working_directory   VARCHAR(500),                   -- 工作目录

    -- 自动化配置
    automation_engine   VARCHAR(50) DEFAULT 'pywinauto', -- pywinauto, winappdriver, flaui
    window_title        VARCHAR(255),                   -- 主窗口标题 (用于定位)
    window_class        VARCHAR(255),                   -- 窗口类名 (备用定位)

    -- 脚本管理
    script_path         VARCHAR(500),                   -- MinIO 路径 (HAT YAML)
    script_format       VARCHAR(50) DEFAULT 'hat_yaml', -- hat_yaml, python, robot

    -- 元数据
    tags                JSONB DEFAULT '[]',
    generated_by_agent  BOOLEAN DEFAULT false,

    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW(),

    UNIQUE(project_id, identifier)
);

-- ============================================================
-- 执行节点注册表
-- ============================================================
CREATE TABLE cs_execution_nodes (
    id                  UUID PRIMARY KEY,
    node_name           VARCHAR(255) NOT NULL UNIQUE,   -- 节点标识
    host                VARCHAR(255) NOT NULL,           -- IP 地址
    port                INTEGER NOT NULL DEFAULT 19527,  -- Agent 端口
    status              VARCHAR(50) DEFAULT 'offline',   -- online / offline / busy
    os_version          VARCHAR(100),                    -- Windows 版本
    capabilities        JSONB DEFAULT '{}',              -- 能力标签
    -- 例: {"engines": ["pywinauto", "winappdriver"],
    --      "screens": ["1920x1080"],
    --      "apps": ["AppA", "AppB"]}

    last_heartbeat      TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 执行运行记录
-- ============================================================
CREATE TABLE cs_test_runs (
    id                  UUID PRIMARY KEY,
    project_id          UUID NOT NULL,
    cs_test_id          UUID NOT NULL REFERENCES cs_tests(id),
    execution_node_id   UUID REFERENCES cs_execution_nodes(id),
    identifier          VARCHAR(255),

    status              VARCHAR(50) DEFAULT 'pending',
    execution_config    JSONB DEFAULT '{}',

    total_steps         INTEGER DEFAULT 0,
    passed_steps        INTEGER DEFAULT 0,
    failed_steps        INTEGER DEFAULT 0,
    skipped_steps       INTEGER DEFAULT 0,
    duration_ms         BIGINT,

    report_path         VARCHAR(500),                   -- MinIO Allure 报告路径
    video_path          VARCHAR(500),                   -- MinIO 录屏路径
    error_message       TEXT,

    started_at          TIMESTAMP,
    completed_at        TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW(),

    UNIQUE(project_id, identifier)
);

-- ============================================================
-- 单步执行结果
-- ============================================================
CREATE TABLE cs_test_results (
    id                  UUID PRIMARY KEY,
    cs_test_run_id      UUID NOT NULL REFERENCES cs_test_runs(id),
    cs_test_id          UUID NOT NULL REFERENCES cs_tests(id),

    step_index          INTEGER,                        -- 步骤序号
    step_name           VARCHAR(500),                   -- 步骤名称
    operation_type      VARCHAR(100),                   -- 操作类型 (点击/输入/断言...)

    status              VARCHAR(50),                    -- passed / failed / skipped

    -- 执行详情
    operation_detail    JSONB,                          -- 操作参数
    expected_result     TEXT,                           -- 预期结果
    actual_result       TEXT,                           -- 实际结果
    error_details       JSONB,                          -- 错误详情

    screenshot_before   VARCHAR(500),                   -- MinIO: 操作前截图
    screenshot_after    VARCHAR(500),                   -- MinIO: 操作后截图

    duration_ms         BIGINT,
    retry_count         INTEGER DEFAULT 0,

    created_at          TIMESTAMP DEFAULT NOW()
);
```

### 3.2 Python 模型 (SQLAlchemy)

```python
# backend/app/models/cs_test.py

from sqlalchemy import Column, String, Integer, BigInteger, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import Base, UUIDMixin, TimestampMixin

class CSTest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "cs_tests"

    project_id = Column(UUID, ForeignKey("projects.id"), nullable=False)
    folder_id = Column(UUID, ForeignKey("folders.id"), nullable=True)
    identifier = Column(String(255), nullable=False)
    name = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    # 应用信息
    app_name = Column(String(255), nullable=False)
    app_path = Column(String(500), nullable=False)
    app_args = Column(String(500), nullable=True)
    working_directory = Column(String(500), nullable=True)

    # 自动化配置
    automation_engine = Column(String(50), default="pywinauto")
    window_title = Column(String(255), nullable=True)
    window_class = Column(String(255), nullable=True)

    # 脚本管理
    script_path = Column(String(500), nullable=True)
    script_format = Column(String(50), default="hat_yaml")

    tags = Column(JSONB, default=[])
    generated_by_agent = Column(Boolean, default=False)

    project = relationship("Project", back_populates="cs_tests")
    folder = relationship("Folder", back_populates="cs_tests")
    runs = relationship("CSTestRun", back_populates="cs_test", cascade="all, delete-orphan")


class CSExecutionNode(Base, UUIDMixin):
    __tablename__ = "cs_execution_nodes"

    node_name = Column(String(255), unique=True, nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, default=19527)
    status = Column(String(50), default="offline")
    os_version = Column(String(100), nullable=True)
    capabilities = Column(JSONB, default={})
    last_heartbeat = Column(String(50), nullable=True)


class CSTestRun(Base, UUIDMixin):
    __tablename__ = "cs_test_runs"

    project_id = Column(UUID, ForeignKey("projects.id"), nullable=False)
    cs_test_id = Column(UUID, ForeignKey("cs_tests.id"), nullable=False)
    execution_node_id = Column(UUID, ForeignKey("cs_execution_nodes.id"), nullable=True)
    identifier = Column(String(255), nullable=True)
    status = Column(String(50), default="pending")
    execution_config = Column(JSONB, default={})
    total_steps = Column(Integer, default=0)
    passed_steps = Column(Integer, default=0)
    failed_steps = Column(Integer, default=0)
    skipped_steps = Column(Integer, default=0)
    duration_ms = Column(BigInteger, nullable=True)
    report_path = Column(String(500), nullable=True)
    video_path = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(String(50), nullable=True)
    completed_at = Column(String(50), nullable=True)

    cs_test = relationship("CSTest", back_populates="runs")
    results = relationship("CSTestResult", back_populates="cs_test_run", cascade="all, delete-orphan")


class CSTestResult(Base, UUIDMixin):
    __tablename__ = "cs_test_results"

    cs_test_run_id = Column(UUID, ForeignKey("cs_test_runs.id"), nullable=False)
    cs_test_id = Column(UUID, ForeignKey("cs_tests.id"), nullable=False)
    step_index = Column(Integer, nullable=True)
    step_name = Column(String(500), nullable=True)
    operation_type = Column(String(100), nullable=True)
    status = Column(String(50))
    operation_detail = Column(JSONB, nullable=True)
    expected_result = Column(Text, nullable=True)
    actual_result = Column(Text, nullable=True)
    error_details = Column(JSONB, nullable=True)
    screenshot_before = Column(String(500), nullable=True)
    screenshot_after = Column(String(500), nullable=True)
    duration_ms = Column(BigInteger, nullable=True)
    retry_count = Column(Integer, default=0)

    cs_test_run = relationship("CSTestRun", back_populates="results")
```

---

## 4. 远程执行架构

### 4.1 整体流程

```
平台后端                         Windows 执行节点
────────                         ────────────────

1. 用户点击"执行"
   │
2. CSTestExecutor
   ├─ 创建 CSTestRun (status=pending)
   ├─ 选择可用节点
   │
3. HTTP POST ───────────────►  4. CSAgent 接收任务
   /api/v1/task/run                ├─ 从 MinIO 下载 YAML 脚本
                                   ├─ 启动被测 .exe 应用
                                   │
5. WebSocket ◄────────────────  6. 实时推送步骤进度
   进度更新                         ├─ 每步执行完推送结果
   (backend → frontend)            ├─ 每步截图上传 MinIO
                                   │
                              7. 执行完毕
                                   ├─ 收集截图/日志
                                   ├─ 生成 Allure 结果 JSON
                                   ├─ 上传到 MinIO
                                   │
8. WebSocket ◄────────────────  9. 任务完成通知
   │
10. CSTestExecutor
    ├─ 从 MinIO 取 Allure 结果
    ├─ 写入 CSTestResult 表
    ├─ 生成 Allure HTML 报告
    └─ 更新 CSTestRun (status=completed)
```

### 4.2 Windows Agent 设计

这是一个独立运行的 Python 服务，部署在 Windows 执行节点上：

```python
# windows-agent/cs_test_agent.py
#
# 部署方式: 在 Windows 机器上运行
#   pip install pywinauto fastapi uvicorn httpx
#   python cs_test_agent.py --port 19527 --name node-win-01

import asyncio
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

import httpx
import uvicorn
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from pywinauto import Application, Desktop

# ============================================================
# Agent 配置
# ============================================================
class AgentConfig:
    BACKEND_URL = "http://platform-backend:8000"  # 平台后端地址
    AGENT_NAME = "node-win-01"
    AGENT_PORT = 19527
    HEARTBEAT_INTERVAL = 10  # 心跳间隔 (秒)

app = FastAPI()
current_task = None  # 当前执行的任务

# ============================================================
# 心跳上报
# ============================================================
async def heartbeat_loop():
    """定期向平台后端上报心跳"""
    while True:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{AgentConfig.BACKEND_URL}/api/v2/cs-nodes/heartbeat",
                    json={"node_name": AgentConfig.AGENT_NAME}
                )
        except Exception:
            pass
        await asyncio.sleep(AgentConfig.HEARTBEAT_INTERVAL)

# ============================================================
# 任务执行 API
# ============================================================
class TaskRequest(BaseModel):
    run_id: str
    cs_test_id: str
    script_url: str          # MinIO 预签名 URL
    app_path: str            # .exe 路径
    app_args: str | None = None
    working_directory: str | None = None
    automation_engine: str = "pywinauto"
    window_title: str | None = None
    context_vars: dict = {}  # 环境变量 ({{变量}} 替换)

@app.post("/api/v1/task/run")
async def execute_task(req: TaskRequest, background_tasks: BackgroundTasks):
    """接收来自平台的测试执行任务"""
    background_tasks.add_task(_execute, req)
    return {"status": "accepted", "run_id": req.run_id}

@app.get("/api/v1/task/status")
async def task_status():
    """查询当前任务执行状态"""
    return {"busy": current_task is not None, "current_run_id": current_task}

@app.post("/api/v1/task/cancel")
async def cancel_task():
    """取消当前任务"""
    global current_task
    current_task = None
    return {"status": "cancelled"}

# ============================================================
# 核心执行逻辑
# ============================================================
async def _execute(req: TaskRequest):
    global current_task
    current_task = req.run_id

    try:
        await _notify_backend(req.run_id, "running")

        # 1. 下载 YAML 脚本
        async with httpx.AsyncClient() as client:
            resp = await client.get(req.script_url)
            yaml_content = resp.text

        # 2. 写入临时工作目录
        workspace = Path(tempfile.mkdtemp(prefix=f"cs_test_{req.run_id}_"))
        (workspace / "context.yaml").write_text(
            _render_context(req.context_vars)
        )
        (workspace / "test_case.yaml").write_text(yaml_content)

        # 3. 启动被测应用
        app = _start_application(req)

        # 4. 执行 HAT YAML (使用桌面操作关键字的本地 HAT runner)
        results = await _run_hat_yaml_with_desktop_keywords(
            workspace, req, app
        )

        # 5. 生成 Allure 结果
        allure_dir = workspace / "allure-results"
        _generate_allure_results(results, allure_dir)

        # 6. 上传结果到 MinIO
        await _upload_results(req.run_id, workspace, allure_dir)

        # 7. 通知平台完成
        await _notify_backend(req.run_id, "completed", {
            "total_steps": len(results),
            "passed_steps": sum(1 for r in results if r["status"] == "passed"),
            "failed_steps": sum(1 for r in results if r["status"] == "failed"),
            "allure_dir": f"cs-test-results/{req.run_id}/",
        })

    except Exception as e:
        await _notify_backend(req.run_id, "failed", {"error": str(e)})
    finally:
        current_task = None
        # 可选: 清理 workspace

# ============================================================
# 应用启动
# ============================================================
def _start_application(req: TaskRequest):
    """启动被测 Windows 桌面应用"""
    if req.automation_engine == "pywinauto":
        if req.app_args:
            app = Application(backend="uia").start(
                f'"{req.app_path}" {req.app_args}',
                work_dir=req.working_directory
            )
        else:
            app = Application(backend="uia").start(req.app_path)

        # 等待主窗口出现
        if req.window_title:
            dlg = app.window(title=req.window_title)
            dlg.wait("visible", timeout=30)
        return app

    elif req.automation_engine == "winappdriver":
        # WinAppDriver 通过 HTTP 与 Appium 协议交互
        # 需要先启动 WinAppDriver.exe 服务
        ...
    return None

# ============================================================
# 桌面操作关键字执行器
# ============================================================
async def _run_hat_yaml_with_desktop_keywords(workspace, req, app):
    """
    解析 HAT YAML 中的桌面操作步骤并逐条执行。

    不走 pytest/HAT TestRunner，直接在 Agent 端解析 YAML +
    调用 pywinauto 执行，因为这里的关键字操作对象是 Windows 桌面控件，
    与后端 HAT 的 HTTP 关键字完全不同。
    """
    import yaml

    with open(workspace / "test_case.yaml", "r", encoding="utf-8") as f:
        case_data = yaml.safe_load(f)

    steps = case_data.get("测试步骤", [])
    results = []
    driver = DesktopActionDriver(app, req.window_title)

    for i, step in enumerate(steps):
        operation = step.get("操作类型")
        step_name = step.get("步骤描述", f"Step {i+1}")

        screenshot_before = await driver.screenshot(f"step_{i}_before")

        try:
            result_data = await driver.execute(operation, step)
            status = "passed"
            actual = result_data
            error = None
        except Exception as e:
            status = "failed"
            actual = None
            error = {"message": str(e), "type": type(e).__name__}

        screenshot_after = await driver.screenshot(f"step_{i}_after")

        results.append({
            "step_index": i + 1,
            "step_name": step_name,
            "operation_type": operation,
            "status": status,
            "operation_detail": step,
            "expected_result": step.get("预期结果", ""),
            "actual_result": str(actual) if actual else None,
            "error_details": error,
            "screenshot_before": screenshot_before,
            "screenshot_after": screenshot_after,
        })

        # 逐步骤实时推送
        await _notify_backend_step(req.run_id, results[-1])

        if status == "failed":
            break  # 或根据 continue_on_failure 决定

    return results

# ============================================================
# 通知后端
# ============================================================
async def _notify_backend(run_id: str, status: str, data: dict = None):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{AgentConfig.BACKEND_URL}/api/v2/cs-tests/runs/{run_id}/callback",
            json={"status": status, **(data or {})}
        )

async def _notify_backend_step(run_id: str, step_result: dict):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{AgentConfig.BACKEND_URL}/api/v2/cs-tests/runs/{run_id}/step-callback",
            json=step_result
        )


if __name__ == "__main__":
    # 注册到平台
    print(f"Agent {AgentConfig.AGENT_NAME} starting on port {AgentConfig.AGENT_PORT}...")
    asyncio.get_event_loop().create_task(heartbeat_loop())
    uvicorn.run(app, host="0.0.0.0", port=AgentConfig.AGENT_PORT)
```

### 4.3 桌面操作驱动 (DesktopActionDriver)

```python
# windows-agent/desktop_action_driver.py

from pywinauto import Application, Desktop, keyboard, mouse
from pywinauto.timings import Timings
from PIL import ImageGrab
import time


class DesktopActionDriver:
    """
    将 HAT YAML 中的"操作类型"映射为 pywinauto 桌面操作。

    HAT YAML 关键字 → pywinauto 调用
    ──────────────────────────────────
    桌面点击     → window[control].click()
    桌面输入     → window[control].set_text()
    桌面获取文本  → window[control].window_text()
    桌面截图     → ImageGrab.grab()
    桌面等待控件  → window[control].wait('visible')
    桌面断言包含  → assert text in control.window_text()
    桌面按键     → keyboard.send_keys()
    桌面选择下拉  → window[combo].select()
    """

    def __init__(self, app: Application, window_title: str = None):
        self.app = app
        self.window_title = window_title
        self._main_window = None
        if window_title:
            self._main_window = app.window(title=window_title)

    def _get_window(self, step: dict):
        """获取步骤指定的窗口，默认用主窗口"""
        title = step.get("窗口标题", self.window_title)
        if title:
            return self.app.window(title=title)
        return self._main_window or Desktop(backend="uia")

    def _find_control(self, window, step: dict):
        """
        按多种策略定位控件，优先级:
        1. automation_id (推荐，最稳定)
        2. 控件名称 (标题文本)
        3. 控件类型 + 名称
        4. class_name
        """
        auto_id = step.get("控件ID")
        name = step.get("控件名称")
        ctrl_type = step.get("控件类型")   # Button, Edit, ComboBox, Text...
        class_name = step.get("控件类名")

        if auto_id:
            return window.child_window(auto_id=auto_id)
        elif name and ctrl_type:
            return window.child_window(title=name, control_type=ctrl_type)
        elif name:
            return window.child_window(title=name)
        elif class_name:
            return window.child_window(class_name=class_name)
        return window

    async def execute(self, operation: str, step: dict):
        window = self._get_window(step)
        control = self._find_control(window, step)
        timeout = float(step.get("超时时间", 10))

        if operation == "桌面启动应用":
            path = step.get("应用路径")
            args = step.get("启动参数", "")
            self.app = Application(backend="uia").start(f'"{path}" {args}')
            title = step.get("窗口标题")
            if title:
                self._main_window = self.app.window(title=title)
                self._main_window.wait("visible", timeout=timeout)
            return {"pid": self.app.process}

        elif operation == "桌面点击":
            # 先等待控件可用
            control.wait("enabled", timeout=timeout)
            control.click()
            return {"clicked": True}

        elif operation == "桌面双击":
            control.wait("enabled", timeout=timeout)
            control.double_click()
            return {"double_clicked": True}

        elif operation == "桌面右键":
            control.wait("enabled", timeout=timeout)
            control.right_click()
            return {"right_clicked": True}

        elif operation == "桌面输入":
            text = step.get("输入内容", "")
            control.wait("enabled", timeout=timeout)
            control.set_text(text)
            return {"text_entered": text}

        elif operation == "桌面清空并输入":
            text = step.get("输入内容", "")
            control.wait("enabled", timeout=timeout)
            control.set_text("")  # 先清空
            control.type_keys(text)  # 逐字输入 (触发输入法事件)
            return {"text_entered": text}

        elif operation == "桌面获取文本":
            text = control.window_text()
            return {"text": text}

        elif operation == "桌面选择下拉":
            value = step.get("选择项", "")
            control.wait("enabled", timeout=timeout)
            control.select(value)
            return {"selected": value}

        elif operation == "桌面勾选":
            control.wait("enabled", timeout=timeout)
            control.check()
            return {"checked": True}

        elif operation == "桌面取消勾选":
            control.wait("enabled", timeout=timeout)
            control.uncheck()
            return {"unchecked": True}

        elif operation == "桌面等待控件":
            control.wait("visible", timeout=timeout)
            return {"visible": True}

        elif operation == "桌面等待消失":
            control.wait_not("visible", timeout=timeout)
            return {"disappeared": True}

        elif operation == "桌面按键":
            keys = step.get("按键", "")
            keyboard.send_keys(keys)
            return {"keys_sent": keys}

        elif operation == "桌面快捷键":
            keys = step.get("组合键", "")  # 如 "^a" (Ctrl+A), "%{F4}" (Alt+F4)
            keyboard.send_keys(keys)
            return {"shortcut": keys}

        elif operation == "桌面断言存在":
            assert control.exists(), f"控件不存在: {step.get('控件名称', 'unknown')}"
            return {"exists": True}

        elif operation == "桌面断言文本包含":
            text = control.window_text()
            expected = step.get("期望值", "")
            assert expected in text, f"期望包含 '{expected}', 实际: '{text}'"
            return {"actual": text, "expected": expected}

        elif operation == "桌面断言文本相等":
            text = control.window_text()
            expected = step.get("期望值", "")
            assert text == expected, f"期望 '{expected}', 实际: '{text}'"
            return {"actual": text, "expected": expected}

        elif operation == "桌面断言启用":
            assert control.is_enabled(), f"控件未启用"
            return {"enabled": True}

        elif operation == "桌面断言可见":
            assert control.is_visible(), f"控件不可见"
            return {"visible": True}

        elif operation == "桌面截图":
            filename = step.get("文件名", f"screenshot_{int(time.time())}.png")
            img = ImageGrab.grab()
            img.save(filename)
            return {"screenshot": filename}

        elif operation == "桌面关闭应用":
            self.app.kill()
            return {"killed": True}

        else:
            raise ValueError(f"不支持的桌面操作类型: {operation}")

    async def screenshot(self, name: str) -> str:
        """截图并返回文件路径"""
        filename = f"{name}_{int(time.time()*1000)}.png"
        img = ImageGrab.grab()
        img.save(filename)
        return filename
```

---

## 5. HAT YAML 测试用例设计

### 5.1 桌面操作关键字清单

```
┌──────────────────────┬────────────────────────────────────┐
│ 操作类型              │ 说明                                │
├──────────────────────┼────────────────────────────────────┤
│ 桌面启动应用          │ 启动被测 .exe                        │
│ 桌面关闭应用          │ 关闭被测应用                         │
│ 桌面点击              │ 左键单击控件                         │
│ 桌面双击              │ 左键双击控件                         │
│ 桌面右键              │ 右键单击控件 (弹出菜单)              │
│ 桌面输入              │ 向输入框设置文本                     │
│ 桌面清空并输入        │ 清空后逐字输入 (触发实时校验)        │
│ 桌面选择下拉          │ 下拉框选择指定项                     │
│ 桌面勾选 / 桌面取消勾选│ 复选框操作                          │
│ 桌面按键              │ 发送按键                            │
│ 桌面快捷键            │ 发送组合键 (Ctrl+A 等)               │
│ 桌面等待控件          │ 等待控件出现                        │
│ 桌面等待消失          │ 等待控件消失                        │
│ 桌面获取文本          │ 读取控件文本内容                     │
│ 桌面截图              │ 全屏截图                            │
│ 桌面断言存在          │ 断言控件存在                        │
│ 桌面断言文本包含      │ 断言控件文本包含指定字符串           │
│ 桌面断言文本相等      │ 断言控件文本等于指定值               │
│ 桌面断言启用          │ 断言控件处于启用状态                 │
│ 桌面断言可见          │ 断言控件可见                        │
└──────────────────────┴────────────────────────────────────┘
```

### 5.2 控件定位策略

YAML 步骤中按优先级使用以下方式定位 Windows 控件：

```yaml
# 方式 1: automation_id (最稳定，推荐)
- 操作类型: 桌面点击
  控件ID: "btnLogin"              # 对应 Windows AutomationId

# 方式 2: 控件名称
- 操作类型: 桌面点击
  控件名称: "登录"

# 方式 3: 控件类型 + 名称
- 操作类型: 桌面输入
  控件类型: "Edit"
  控件名称: "用户名"

# 方式 4: 控件类名
- 操作类型: 桌面点击
  控件类名: "Button"
```

控件定位信息可通过 **Inspect.exe** (Windows SDK 自带) 或 **Accessibility Insights** 工具获取。

### 5.3 完整 YAML 示例

```yaml
# 用例: 登录功能测试
# 被测应用: MyApp.exe (Windows 桌面应用)

基础配置:
  用例描述: 验证用户登录流程 - 正确账号登录成功
  用例等级: P0
  用例类型: cs_test
  被测应用: MyApp
  自动化引擎: pywinauto
  窗口标题: "MyApp - 企业版 v3.2"

测试步骤:
  - 操作类型: 桌面启动应用
    步骤描述: 启动被测应用
    应用路径: "C:\\Program Files\\MyApp\\MyApp.exe"
    启动参数: "--lang=zh-CN"
    窗口标题: "MyApp - 企业版 v3.2"
    超时时间: 30

  - 操作类型: 桌面等待控件
    步骤描述: 等待登录窗口出现
    控件ID: "loginWindow"
    超时时间: 15

  - 操作类型: 桌面输入
    步骤描述: 输入用户名
    控件ID: "txtUsername"
    输入内容: "{{TEST_USER}}"

  - 操作类型: 桌面输入
    步骤描述: 输入密码
    控件ID: "txtPassword"
    输入内容: "{{TEST_PASSWORD}}"

  - 操作类型: 桌面点击
    步骤描述: 点击登录按钮
    控件ID: "btnLogin"

  - 操作类型: 桌面等待控件
    步骤描述: 等待主窗口加载
    控件ID: "mainWindow"
    超时时间: 20

  - 操作类型: 桌面断言存在
    步骤描述: 验证主窗口显示
    控件ID: "mainWindow"
    预期结果: 登录成功后显示主窗口

  - 操作类型: 桌面断言文本包含
    步骤描述: 验证用户名显示在标题栏
    控件ID: "lblWelcome"
    期望值: "{{TEST_USER}}"
    预期结果: 标题栏显示当前用户名

  - 操作类型: 桌面截图
    步骤描述: 登录成功后截图
    文件名: "login_success.png"

  - 操作类型: 桌面关闭应用
    步骤描述: 关闭应用

---
# 用例: 登录功能测试 - 错误密码
基础配置:
  用例描述: 验证错误密码登录失败
  用例等级: P1
  用例类型: cs_test

测试步骤:
  - 操作类型: 桌面启动应用
    应用路径: "C:\\Program Files\\MyApp\\MyApp.exe"
    窗口标题: "MyApp - 企业版 v3.2"

  - 操作类型: 桌面输入
    控件ID: "txtUsername"
    输入内容: "admin"

  - 操作类型: 桌面输入
    控件ID: "txtPassword"
    输入内容: "wrong_password"

  - 操作类型: 桌面点击
    控件ID: "btnLogin"

  - 操作类型: 桌面等待控件
    步骤描述: 等待错误提示出现
    控件ID: "errorMsgBox"
    超时时间: 5

  - 操作类型: 桌面断言文本包含
    步骤描述: 验证错误提示内容
    控件ID: "errorMsgLabel"
    期望值: "密码错误"

  - 操作类型: 桌面关闭应用
```

---

## 6. API 路由设计

### 6.1 后端 API

```python
# backend/app/api/v2/cs_tests.py

router = APIRouter(prefix="/projects/{project_identifier}/cs-tests")

# === 测试用例管理 ===
@router.post("")                    # 创建桌面测试用例
@router.get("")                     # 列表 (支持 folder_id / search / page)
@router.get("/{cs_test_id}")        # 详情
@router.patch("/{cs_test_id}")      # 更新
@router.delete("/{cs_test_id}")     # 删除

# === 脚本管理 ===
@router.get("/{cs_test_id}/script")     # 下载 YAML 脚本
@router.put("/{cs_test_id}/script")     # 上传 YAML 脚本

# === 执行 ===
@router.post("/{cs_test_id}/run")       # 提交执行任务 → 分发到 Windows 节点
@router.get("/{cs_test_id}/runs")       # 执行历史
@router.get("/{cs_test_id}/runs/{run_id}")         # 运行详情
@router.get("/{cs_test_id}/runs/{run_id}/results")  # 步骤结果列表

# === 执行回调 (Windows Agent → Backend) ===
@router.post("/runs/{run_id}/callback")      # Agent 回调: 任务状态更新
@router.post("/runs/{run_id}/step-callback")  # Agent 回调: 单步结果

# === 文件夹 ===
@router.get("/folder/{folder_id}")    # 文件夹下测试列表

# === 节点管理 ===
router_nodes = APIRouter(prefix="/cs-nodes")

@router_nodes.get("")                 # 节点列表
@router_nodes.post("/register")       # 节点注册
@router_nodes.post("/heartbeat")      # 节点心跳
@router_nodes.get("/{node_id}")       # 节点详情
@router_nodes.delete("/{node_id}")    # 注销节点
```

### 6.2 路由注册

```python
# backend/app/api/v2/__init__.py
from . import cs_tests

v2_router.include_router(cs_tests.router)
v2_router.include_router(cs_tests.router_nodes)
```

---

## 7. 前端 UI 设计

### 7.1 页面结构

```
ui/app/projects/[projectId]/cs-tests/page.tsx
ui/components/cs-tests/
├── index.ts
├── CSTestList.tsx                    -- 测试列表 (带文件夹树)
├── CSTestDialog.tsx                  -- 创建/编辑对话框
│   ├── 应用配置区 (app_path, args, window_title)
│   ├── 自动化配置区 (engine 选择)
│   └── 脚本预览区
├── CSYAMLEditor.tsx                  -- Monaco YAML 编辑器
├── CSExecutionPanel.tsx              -- 执行面板
│   ├── 节点选择下拉
│   ├── 环境变量输入
│   └── 执行按钮 + 实时进度条
├── CSRunHistory.tsx                  -- 运行历史列表
├── CSStepResultViewer.tsx            -- 步骤结果详情
│   ├── 操作前/后截图对比
│   ├── 操作详情 JSON
│   └── 错误堆栈
└── CSNodeManager.tsx                 -- 节点管理页 (可选)
    ├── 节点列表 (在线/离线/忙碌)
    └── 节点能力标签展示
```

### 7.2 核心交互流程

```
1. 用户进入 C/S 测试页面
2. 左侧文件夹树 → 选择文件夹
3. 中间测试列表 → 选择/创建测试
4. 右侧三 Tab:
   [编辑器] ─ YAML 脚本编辑 (Monaco)
   [执行]   ─ 选择 Windows 节点 → 输入变量 → 点击执行
             → 实时进度条 (通过 WebSocket 推送)
             → 步骤逐条显示 (带截图)
   [AI]     ─ AI 对话面板 (Agent 辅助生成脚本)
```

---

## 8. HAT 关键字集成方式

### 8.1 为什么不用后端 HAT 执行

| 后端 HAT (现有) | 桌面 HAT (新增) |
|----------------|----------------|
| 运行在 Linux/macOS | 运行在 Windows |
| 关键字操作 HTTP | 关键字操作 Windows 控件 |
| 使用 requests 库 | 使用 pywinauto |
| 通过 pytest 调用 | 在 Agent 端独立解析 YAML |

结论：桌面测试的 HAT YAML **不是由后端 run_hat.py 执行**，而是在 Windows Agent 端独立解析和执行。YAML 格式保持一致（复用 YAML 结构、context.yaml 变量替换、Allure 结果格式），但执行引擎完全独立。

### 8.2 复用点

```
复用的部分:
├── YAML 格式: 基础配置 + 测试步骤 (相同结构)
├── context.yaml: 变量注入机制 ({{变量名}})
├── 文件夹管理: 同一套 Folder 表
├── Allure 结果格式: 统一的 allure-results JSON
├── MinIO 存储: 脚本 + 截图 + 报告 使用同一套存储

独立的部分:
├── 执行引擎: Windows Agent 端独立运行，不通过 run_hat.py
├── 关键字集: 完全是新的桌面操作关键字
├── 执行环境: Windows 独立进程，通过 HTTP 回调通信
└── 结果采集: 每步截图 + 录屏 (Web/API 测试不需要)
```

---

## 9. 部署架构

### 9.1 环境要求

```
┌─────────────────────────────────────────────────────┐
│ 平台后端 (不变)                                      │
│   Linux/macOS                                       │
│   Python 3.13+ + FastAPI + PostgreSQL + MinIO       │
│   docker-compose up                                 │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Windows 执行节点 (新增)                              │
│   Windows 10/11 或 Windows Server 2019+             │
│                                                     │
│   安装:                                              │
│     Python 3.11+                                    │
│     pip install pywinauto uvicorn httpx pillow      │
│                                                     │
│   启动 Agent:                                        │
│     python cs_test_agent.py \                       │
│       --name node-win-01 \                          │
│       --port 19527 \                                │
│       --backend http://platform:8000                │
│                                                     │
│   可选:                                              │
│     - WinAppDriver (MS 官方，支持更多控件类型)       │
│     - Inspect.exe (Windows SDK, 用于识别控件 ID)    │
│     - FFmpeg (录屏)                                  │
└─────────────────────────────────────────────────────┘
```

### 9.2 网络拓扑

```
                    ┌──────────────┐
                    │  用户浏览器   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Next.js     │
                    │  :3000       │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  FastAPI     │
                    │  :8000       │
                    └──┬───────┬──┘
                       │       │
              ┌────────▼──┐ ┌──▼──────────┐
              │ PostgreSQL │ │ MinIO       │
              │ :5432      │ │ :9000       │
              └────────────┘ └──┬──────────┘
                                │ 截图/脚本/报告
                                │
    ┌───────────────────────────┼───────────────────────┐
    │                           │                       │
┌───▼────────┐          ┌──────▼──────┐        ┌───────▼──────┐
│ Windows #1 │          │ Windows #2  │        │ Windows #3   │
│ Agent:19527│          │ Agent:19527 │        │ Agent:19527  │
│ MyApp.exe  │          │ MyApp.exe   │        │ 其他App.exe  │
└────────────┘          └─────────────┘        └──────────────┘
```

Windows 节点需要与平台后端的 **8000 端口** 和 **MinIO 9000 端口** 网络互通。

---

## 10. 实施路线图

### 阶段 1: Windows Agent 原型 (3-4 天)

| 任务 | 说明 |
|------|------|
| DesktopActionDriver | 实现 20 个桌面操作关键字 |
| YAML 解析器 | 独立解析 HAT YAML + context.yaml 变量替换 |
| 截图集成 | 每步前后截图，PIL ImageGrab |
| Agent HTTP 服务 | FastAPI 服务，接收 /task/run |
| 与后端通信 | 心跳 + 任务回调 |
| 手动验证 | 在一台 Windows 机器上跑通一个完整用例 |

### 阶段 2: 后端模型 + API (2-3 天)

| 任务 | 文件 |
|------|------|
| 数据模型 | `models/cs_test.py` (CSTest, CSTestRun, CSTestResult, CSExecutionNode) |
| 仓库 | `repositories/cs_test_repo.py` |
| Schema | `schemas/cs_test.py` |
| 服务层 | `services/cs_test_service.py` (CRUD + 节点选择 + 任务分发) |
| API 路由 | `api/v2/cs_tests.py` |
| 回调处理 | 接收 Agent 的状态/步骤回调，写入 DB，推送 WebSocket |
| 路由注册 | `api/v2/__init__.py` |
| 数据库迁移 | Alembic 迁移 |

### 阶段 3: 前端 (3-4 天)

| 任务 | 说明 |
|------|------|
| API 客户端 | `ui/lib/api/cs-tests.ts` |
| 主页面 | 页面框架 + 三栏布局 |
| 测试列表 + 文件夹树 | 复用现有 FolderTree 组件 |
| 创建/编辑对话框 | 应用配置 + 自动化配置表单 |
| YAML 编辑器 | Monaco Editor 集成 |
| 执行面板 | 节点选择 + 环境变量 + 实时进度 (WebSocket) |
| 步骤结果查看器 | 截图对比 + 操作详情 |

### 阶段 4: 完善 (2-3 天)

| 任务 | 说明 |
|------|------|
| 录屏功能 | FFmpeg 录屏，上传 MinIO |
| 多节点调度 | 负载均衡选择空闲节点 |
| 节点管理 UI | 节点列表 + 在线状态 |
| 失败重试 | 失败步骤自动重试 |
| 异常恢复 | Agent 崩溃后任务状态恢复 |

### 阶段 5: AI Agent (可选, 3-4 天)

| 任务 | 说明 |
|------|------|
| CS Agent | LangGraph Agent，理解桌面应用操作 |
| 控件识别工具 | 从应用截图/文档识别控件 ID |
| YAML 生成工具 | 从测试计划生成 HAT YAML |
| graph.json | 注册 cs agent |

---

## 11. 关键决策对比

### 11.1 自动化引擎选择

| 引擎 | 优势 | 劣势 | 适用场景 |
|------|------|------|---------|
| **pywinauto** | Python 原生，轻量，无额外依赖 | 部分 WPF/UWP 控件支持弱 | Win32, WinForms 应用 |
| **WinAppDriver** | 微软官方，Appium 协议，支持 UWP/WPF | 需要额外安装服务，启动慢 | WPF, UWP, 现代 WinUI |
| **FlaUI** | .NET 生态，控件支持最全 | 需要 .NET runtime，Python 调用需 IPC | 复杂企业应用 |

**推荐**：默认使用 **pywinauto (UIA backend)**，通过 `automation_engine` 字段支持切换。

### 11.2 脚本格式选择

| 格式 | 优势 | 劣势 |
|------|------|------|
| **HAT YAML** (推荐) | 与平台统一，可复用编辑器、AI 生成 | 需要 Windows 端独立解析 |
| Python 脚本 | 灵活，直接调 pywinauto | 需要编码能力，不易 AI 生成 |
| Robot Framework | 成熟的关键字驱动框架 | 引入额外框架，与 HAT 冗余 |

**推荐**：HAT YAML 格式，与现有体系统一，底层映射到桌面操作关键字。

---

## 12. 架构总结

```
┌─────────────────────────────────────────────────────────────┐
│                     平台后端 (不变)                          │
│                                                             │
│  CSTestService ─► CSTestExecutor ─► CSExecutionNodeManager  │
│       │                │                    │               │
│       │          选择可用节点           心跳/注册            │
│       │                │                    │               │
│       ▼                ▼                    ▼               │
│  ┌─────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │ PG 存储  │   │ HTTP 任务下发 │   │ WebSocket 推送│       │
│  └─────────┘   └──────┬───────┘   └──────┬───────┘        │
│                       │                  │                 │
└───────────────────────┼──────────────────┼─────────────────┘
                        │                  │
        ┌───────────────┼──────────────────┼───────────┐
        │               ▼                  ▼           │
        │  ┌──────────────────────────────────────┐    │
        │  │        Windows 执行节点               │    │
        │  │                                      │    │
        │  │  CSAgent (FastAPI :19527)            │    │
        │  │  ├─ 接收 YAML 脚本                   │    │
        │  │  ├─ 启动被测 .exe                    │    │
        │  │  ├─ DesktopActionDriver 逐条执行     │    │
        │  │  │   ├─ 桌面点击/输入/断言...        │    │
        │  │  │   └─ pywinauto → Windows UI       │    │
        │  │  ├─ 逐步骤回调结果 + 截图             │    │
        │  │  └─ 上传 Allure 结果到 MinIO         │    │
        │  └──────────────────────────────────────┘    │
        │                                              │
        │  ┌────────────────────┐                      │
        │  │ 被测 .exe 应用     │                      │
        │  │ (Windows 桌面 GUI) │                      │
        │  └────────────────────┘                      │
        └──────────────────────────────────────────────┘
```

核心思路：**后端管管理、AI 管生成、Windows Agent 管执行**。YAML 格式和 Allure 报告体系与现有平台完全统一，桌面 UI 操作的具体执行由独立的 Windows Agent 进程完成。
