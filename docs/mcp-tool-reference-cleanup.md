# MCP 工具引用清理方案

> 背景：项目最初设计 api_planner / api_generator / api_healer 作为 MCP server 工具，实际开发中这些能力已由 SkillsMiddleware（hat-test-planner / hat-test-generator / hat-test-healer / hat-test-reporter）替代，但代码中仍保留了过时的 MCP 引用。本方案清理所有不准确的引用，消除误导。

**涉及文件：4 个，改动点：14 处，全部为注释/文本修改，零逻辑变更。**

---

## 文件 1：agent.py — 删除无用 import

**位置：** `backend/app/agents/api/agent.py` 第 35-36 行

**现状：** 导入了但从未使用

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
```

**修改方式：** 直接删除两行 import 语句。不影响任何功能。

---

## 文件 2：tool_registry.py — 更正误导性注释

**位置：** `backend/app/agents/api/tool_registry.py` 第 10-12 行

**现状：**

```python
注意：MCP 工具（api_planner, api_generator, api_healer, chart）
在 agent.py 的 make_agent() 中异步加载，不在此处定义。
```

**改为：**

```python
注意：API Agent 的领域能力由 SkillsMiddleware 按需加载，对应 skill 路径：
  - hat-test-planner   → /hat_skills/hat-test-planner   （替代原 api_planner）
  - hat-test-generator → /hat_skills/hat-test-generator （替代原 api_generator）
  - hat-test-healer    → /hat_skills/hat-test-healer    （替代原 api_healer）
  - hat-test-reporter  → /hat_skills/hat-test-reporter  （替代原 chart）
上述 skill 由 agent.py 中 SkillsMiddleware 加载，不在此处定义。
```

---

## 文件 3：batch_tools.py — 修正 Agent 工作流指引文本

**位置：** `backend/app/agents/api/tools/batch_tools.py`

这部分改动影响最大，因为 workflow 字段是 Agent 直接读取的执行指引。

### 改动 1：docstring（第 42 行）

**现状：**

```python
    返回的端点信息可用于后续调用 api_generator 逐个生成测试。
```

**改为：**

```python
    返回的端点信息可用于后续参考 hat-test-generator skill 逐个生成测试。
```

### 改动 2：workflow 指引，batch_generate_tests 返回值（第 113-118 行）

**现状：**

```python
"workflow": [
    "1. 对每个端点调用 get_endpoint_details 获取详情",
    "2. 调用 api_planner 生成测试计划",
    "3. 调用 api_generator 生成测试代码",
    "4. 调用 save_test_plan/save_test_script 保存成果物"
]
```

**改为：**

```python
"workflow": [
    "1. 对每个端点调用 get_endpoint_details 获取详情",
    "2. 参考 hat-test-planner skill 生成测试计划",
    "3. 参考 hat-test-generator skill 生成测试代码",
    "4. 调用 save_test_plan/save_test_script 保存成果物"
]
```

### 改动 3：workflow 指引，batch_run_tests 返回值（第 211-215 行）

**现状：**

```python
"workflow": [
    "1. 调用 run_test_suite 执行所有测试",
    "2. 分析测试结果",
    "3. 对失败的测试调用 api_healer 修复"
]
```

**改为：**

```python
"workflow": [
    "1. 调用 run_test_suite 执行所有测试",
    "2. 分析测试结果",
    "3. 对失败的测试参考 hat-test-healer skill 修复"
]
```

---

## 文件 4：test_artifacts_tools.py — 修正 docstring

**位置：** `backend/app/agents/api/tools/test_artifacts_tools.py`

### save_test_plan 工具

#### 改动 1：方法 docstring（第 99 行）

**现状：**

```python
    1. 通过 plan_path 指定由 api_planner 生成的测试计划文件路径
```

**改为：**

```python
    1. 通过 plan_path 指定测试计划文件路径（参考 hat-test-planner skill 生成）
```

#### 改动 2：参数说明（第 105 行）

**现状：**

```python
        plan_path: 测试计划文件路径（由 api_planner 生成），如 "./api-test-plan.md"
```

**改为：**

```python
        plan_path: 测试计划文件路径，如 "./api-test-plan.md"
```

#### 改动 3：注释（第 130 行）

**现状：**

```python
        # 从 api_planner 生成的文件读取
```

**改为：**

```python
        # 从文件读取
```

### save_test_script 工具

#### 改动 4：方法 docstring（第 360 行）

**现状：**

```python
    1. 通过 script_path 指定由 api_generator 生成的脚本文件路径
```

**改为：**

```python
    1. 通过 script_path 指定脚本文件路径（参考 hat-test-generator skill 生成）
```

#### 改动 5：参数说明（第 365 行）

**现状：**

```python
        script_path: 脚本文件路径（由 api_generator 生成）
```

**改为：**

```python
        script_path: 脚本文件路径
```

#### 改动 6：注释（第 382 行）

**现状：**

```python
        # 从 api_generator 生成的文件读取
```

**改为：**

```python
        # 从文件读取
```

---

## 改动矩阵

| # | 文件 | 行号 | 类型 | 旧文本（片段） | 新文本（片段） | 影响 |
|---|------|------|------|--------------|--------------|------|
| 1 | agent.py | 35 | import | `from langchain_mcp_adapters.client import MultiServerMCPClient` | 删除 | 无 |
| 2 | agent.py | 36 | import | `from langchain_mcp_adapters.tools import load_mcp_tools` | 删除 | 无 |
| 3 | tool_registry.py | 10-12 | 注释 | `MCP 工具（api_planner, api_generator...）在 agent.py 中异步加载` | 改为 Skills 说明 | 无 |
| 4 | batch_tools.py | 42 | docstring | `调用 api_generator 逐个生成测试` | `参考 hat-test-generator skill` | 低 |
| 5 | batch_tools.py | 115 | workflow | `调用 api_planner 生成测试计划` | `参考 hat-test-planner skill` | 低 |
| 6 | batch_tools.py | 116 | workflow | `调用 api_generator 生成测试代码` | `参考 hat-test-generator skill` | 低 |
| 7 | batch_tools.py | 214 | workflow | `调用 api_healer 修复` | `参考 hat-test-healer skill` | 低 |
| 8 | test_artifacts_tools.py | 99 | docstring | `由 api_planner 生成的测试计划文件路径` | `测试计划文件路径（参考 hat-test-planner skill 生成）` | 无 |
| 9 | test_artifacts_tools.py | 105 | docstring | `plan_path: 测试计划文件路径（由 api_planner 生成）` | `plan_path: 测试计划文件路径` | 无 |
| 10 | test_artifacts_tools.py | 130 | 注释 | `# 从 api_planner 生成的文件读取` | `# 从文件读取` | 无 |
| 11 | test_artifacts_tools.py | 360 | docstring | `由 api_generator 生成的脚本文件路径` | `脚本文件路径（参考 hat-test-generator skill 生成）` | 无 |
| 12 | test_artifacts_tools.py | 365 | docstring | `script_path: 脚本文件路径（由 api_generator 生成）` | `script_path: 脚本文件路径` | 无 |
| 13 | test_artifacts_tools.py | 382 | 注释 | `# 从 api_generator 生成的文件读取` | `# 从文件读取` | 无 |

---

## 附：善后选项（可选清理）

以下两项属于"既然改了不如一并清理"的内容：

### 可选 1：删除 settings.py 中无用的 mcp_root 配置

`backend/app/config/settings.py` 中定义了多个 `*_mcp_root` 字段：

```python
api_mcp_root: str = "backend/mcp/api"      # 指向不存在的目录
perf_mcp_root: str = "backend/mcp/perf"    # 指向不存在的目录  
web_mcp_root: str = "backend/mcp/web"      # 指向不存在的目录
web_chrome_mcp_root: str = "backend/mcp/web_chrome"  # 指向不存在的目录
```

当前除 KG 外，所有 Agent 的 MCP server 均未实现。这些配置目前没有代码引用（grep 结果只出现在 settings.py 自身），可以保留作为未来扩展预留，或删除。

### 可选 2：删除 .env 中的 MCP 环境变量

```env
API_MCP_ROOT=backend/mcp/api
WEB_MCP_ROOT=backend/mcp/web
WEB_CHROME_MCP_ROOT=backend/mcp/web_chrome
PERF_MCP_ROOT=backend/mcp/perf
```

如果 settings.py 中的同名配置也删除了，这些环境变量自动失效。否则它们只是被覆盖，无实际影响。

---

## 修改后验证

1. 确认 `agent.py` 启动正常 — 删除 import 后 `make_agent()` 仍可正常创建 Agent
2. 确认 `batch_generate_tests` 和 `batch_run_tests` 返回的 workflow 字段已更新
3. 确认系统 prompt 中引用的 Skill 名称与文件路径一致
