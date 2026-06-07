"""
API Agent Subagent 定义

主协调者通过 task() 工具委派给专用 subagent，隔离上下文、缩小工具集。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.agents.api.tool_registry import BATCH_TOOLS, SCENARIO_TOOLS

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware

HAT_SKILLS_ROOT = "/hat_skills/"

# 各 subagent 按需加载的 skill 路径
SKILL_PLANNER = f"{HAT_SKILLS_ROOT}hat-test-planner/"
SKILL_GENERATOR = f"{HAT_SKILLS_ROOT}hat-test-generator/"
SKILL_SCENARIO = f"{HAT_SKILLS_ROOT}hat-test-scenario/"
SKILL_EXECUTOR = f"{HAT_SKILLS_ROOT}hat-test-executor/"
SKILL_REPORTER = f"{HAT_SKILLS_ROOT}hat-test-reporter/"
SKILL_HEALER = f"{HAT_SKILLS_ROOT}hat-test-healer/"

_CONTEXT_HINT = """
运行时上下文由系统注入，调用工具时使用 project_identifier 和 folder_id，不要向用户索取。
返回给主协调者的结果保持简洁（摘要、路径、通过/失败数），不要粘贴完整 YAML 或 Allure 原始输出。
"""

_HAT_CONSTRAINTS = """
HAT 硬性约束：
- 路径格式：tests/{project_identifier}/api-tests/{case_slug}/（workspace 相对路径）
- **禁止** write_file / edit_file 部署 HAT YAML；必须用 deploy_hat_case（单端点）或 deploy_hat_scenario（场景）
- 禁止 /home/...、backend/workspace/... 等绝对路径
- context.yaml 中 URL 使用 {{API_BASE_URL}}，禁止替换为真实地址
- 用例文件命名 0_*.yaml、1_*.yaml；禁止 config:/tests: 结构
- 已有脚本只读不写（增量生成）
"""


class ScenarioPlan(BaseModel):
    """hat-scenario subagent 结构化输出"""

    scenario_name: str = Field(description="场景名称")
    case_slug: str = Field(description="用例目录 slug，如 scenario_conversation_flow")
    yaml_sequence: list[str] = Field(description="有序 YAML 文件名列表")
    shared_vars: dict[str, str] = Field(
        default_factory=dict,
        description="context.yaml 需共享的变量及说明",
    )
    data_flow: str = Field(description="跨文件变量传递说明，300字以内")
    summary: str = Field(description="场景设计摘要，300字以内")


COORDINATOR_PROMPT = """# API 测试协调者（HAT 框架）

你是 API 自动化测试的**协调者**，不亲自生成 YAML、不亲自执行 pytest、不亲自解析 Allure。
通过 `task()` 工具委派给专用 subagent，汇总结果后回复用户。

## 委派规则

| 用户意图 | 委派顺序 |
|----------|----------|
| 单端点生成/测试 | hat-planner → hat-generator → hat-executor |
| 批量端点测试 | 对每个端点：hat-planner → hat-generator；最后 hat-executor 或 batch |
| 跨接口业务流程（场景） | hat-scenario（设计）→ hat-generator（deploy_hat_scenario 部署）→ hat-executor |
| 测试失败修复 | hat-healer → hat-executor（验证） |
| 仅执行已有用例 | hat-executor |
| 数据库场景编排（平台 UI 场景） | db-scenario |

## 判断单端点 vs 场景

- **单端点**：用户给出 endpoint_id，或只测一个接口
- **场景**：描述业务流程、多角色、跨模块链路，或明确要求场景测试

## 你的职责

1. 理解用户意图，选择正确的 subagent 和顺序
2. 用 `get_endpoint_details` / `list_api_endpoints` 获取必要上下文后委派
3. 将上一步 subagent 的关键产出（计划 ID、case_dir、失败摘要）传给下一步
4. **委派前用一句话告知用户**（如「正在委派 hat-executor 执行 scenario_xxx…」），避免长时间无反馈
5. 向用户汇报最终结果，不暴露中间工具的大量原始输出

委派 hat-executor 前先用 list_hat_case_dirs 确认 case_dir 存在，再传入 deploy 返回的完整路径。

## 不要做的事

- 不要用 write_file 写 HAT 用例（会写到错误目录，execute_api_script 找不到）
- 不要自己写 HAT YAML 或修改 workspace 文件（交给 hat-generator / hat-healer）
- 不要自己调用 execute_api_script（交给 hat-executor）
- 不要把 DB 场景工具与 HAT YAML 场景混用（DB 场景走 db-scenario）
"""


from app.agents.api.tools.openapi_tools import (  # noqa: E402
    get_endpoint_details,
    get_multiple_endpoints_details,
    list_api_endpoints,
)
from app.agents.api.tools.test_artifacts_tools import save_test_plan  # noqa: E402
from app.agents.api.tools.test_artifacts_tools import (  # noqa: E402
    deploy_hat_case,
    deploy_hat_scenario,
    deploy_hat_keyword,
    get_artifact_content,
    get_endpoint_artifacts,
    list_hat_case_dirs,
    save_test_script,
)
from app.agents.api.tools.test_execution_tools import parse_test_results  # noqa: E402
from app.agents.api.tools.script_tools import get_api_script_info  # noqa: E402
from app.agents.api.tools.environment_tools import (  # noqa: E402
    get_default_environment,
    list_environments,
)
from app.agents.api.tools.script_execution_tools import execute_api_script  # noqa: E402
from app.agents.api.tools.diagnosis_trigger_tools import diagnose_test_run  # noqa: E402

COORDINATOR_TOOLS = [
    list_api_endpoints,
    get_endpoint_details,
    get_multiple_endpoints_details,
    list_hat_case_dirs,
    list_environments,
    get_default_environment,
    *BATCH_TOOLS,
]


def build_subagents(context_middleware: AgentMiddleware) -> list[dict]:
    """构建 HAT 专用 subagent 列表。"""
    shared_middleware = [context_middleware]

    hat_planner = {
        "name": "hat-planner",
        "description": (
            "分析单个或多个 API 端点，生成含结构化「生成指引」的 HAT 测试计划并保存到数据库。"
            "用于单端点测试或批量测试的计划阶段。"
        ),
        "system_prompt": f"""你是 HAT 测试计划专家。加载 hat-test-planner skill 完成任务。

职责：
1. 获取端点详情（method、path、parameters、request_body、responses、security）
2. 生成含「生成指引」的测试计划
3. save_test_plan 保存计划

{_HAT_CONSTRAINTS}
{_CONTEXT_HINT}
""",
        "tools": [get_endpoint_details, get_multiple_endpoints_details, save_test_plan],
        "skills": [SKILL_PLANNER],
        "middleware": shared_middleware,
    }

    hat_generator = {
        "name": "hat-generator",
        "description": (
            "基于测试计划为单个 API 端点增量生成 HAT YAML 脚本，"
            "deploy_hat_case 部署到 workspace，save_test_script 保存元数据。"
            "不覆盖已有脚本。"
        ),
        "system_prompt": f"""你是 HAT YAML 生成专家。加载 hat-test-generator skill 完成任务。

职责：
1. get_endpoint_artifacts 盘点已有脚本（增量：只读不写已有文件）
2. 解析计划中的「生成指引」映射为 YAML 步骤
3. 单端点用 deploy_hat_case；多文件场景用 deploy_hat_scenario（无需 endpoint_id）
4. save_test_script(script_format="hat") 保存元数据

{_HAT_CONSTRAINTS}
{_CONTEXT_HINT}
""",
        "tools": [
            get_endpoint_details,
            get_endpoint_artifacts,
            get_artifact_content,
            deploy_hat_case,
            deploy_hat_scenario,
            deploy_hat_keyword,
            save_test_script,
        ],
        "skills": [SKILL_GENERATOR],
        "middleware": shared_middleware,
    }

    hat_scenario = {
        "name": "hat-scenario",
        "description": (
            "设计跨多个 YAML 文件的业务流程场景测试：拆解文件序列、"
            "设计 context.yaml 数据流与变量传递。不执行测试。"
        ),
        "system_prompt": f"""你是 HAT 场景编排专家。加载 hat-test-scenario skill 完成任务。

职责：
1. 分析业务流程，判断是否需要跨文件编排
2. 设计有序 YAML 序列（0_login.yaml → 1_xxx.yaml → N_cleanup.yaml）
3. 设计 context.yaml 共享变量（统一使用 base_url: "{{{{API_BASE_URL}}}}"）
4. 输出场景设计摘要；YAML 内容由 hat-generator 通过 deploy_hat_scenario 部署

单 YAML 内可完成的链路不需要跨文件拆分。
禁止在本阶段使用 write_file；场景文件统一由 hat-generator + deploy_hat_scenario 写入。

{_HAT_CONSTRAINTS}
{_CONTEXT_HINT}
""",
        "tools": [list_api_endpoints, get_multiple_endpoints_details, list_hat_case_dirs],
        "skills": [SKILL_SCENARIO],
        "response_format": ScenarioPlan,
        "middleware": shared_middleware,
    }

    hat_executor = {
        "name": "hat-executor",
        "description": (
            "目录级执行 HAT YAML 用例（pytest + Allure），"
            "解析测试结果并生成报告摘要。"
        ),
        "system_prompt": f"""你是 HAT 测试执行专家。加载 hat-test-executor 和 hat-test-reporter skill。

职责：
1. execute_api_script(framework="hat", local_script_path=用例目录) 执行
2. parse_test_results 解析 Allure 结果（传入 project_identifier 脱敏 URL）
3. 返回通过/失败摘要、失败用例名、case_dir

**路径硬性要求（最常见失败原因）：**
- local_script_path 必须是单个用例目录，格式：tests/{{project_identifier}}/api-tests/{{case_slug}}/
- 正确示例：tests/PR-1/api-tests/scenario_conversation_flow/
- **禁止** tests、tests/PR-1、tests/PR-1/api-tests 等过宽路径（会触发全量执行并阻塞数分钟）
- 执行前调用 list_hat_case_dirs 确认目录存在
- 若找不到文件，检查是否误用 write_file（应改用 deploy_hat_scenario 重新部署）

环境连接失败时：
- 日志中 {{{{API_BASE_URL}}}} 是脱敏占位符，不要推断为 localhost
- 检查 environment_status.public_api_configured
- 优先检查 YAML 请求地址是否为完整 REST 路径

{_CONTEXT_HINT}
""",
        "tools": [
            list_hat_case_dirs,
            execute_api_script,
            parse_test_results,
            get_default_environment,
            list_environments,
            get_api_script_info,
        ],
        "skills": [SKILL_EXECUTOR, SKILL_REPORTER],
        "middleware": shared_middleware,
    }

    hat_healer = {
        "name": "hat-healer",
        "description": (
            "诊断 HAT YAML 测试失败的 7 类根因（认证/断言/变量/关键字/数据库/YAML语法/环境），"
            "按最小修改原则修复并重新部署。"
        ),
        "system_prompt": f"""你是 HAT 测试修复专家。加载 hat-test-healer skill 完成任务。

职责：
1. 从失败信息分类诊断根因
2. get_artifact_content 读取现有 YAML
3. 最小修改原则修复，deploy_hat_case 重新部署
4. 返回修复摘要（改了什么、为何改）

无法修复时说明原因，建议回退 hat-generator 重新生成。

{_HAT_CONSTRAINTS}
{_CONTEXT_HINT}
""",
        "tools": [
            get_artifact_content,
            deploy_hat_case,
            deploy_hat_scenario,
            diagnose_test_run,
            execute_api_script,
        ],
        "skills": [SKILL_HEALER],
        "middleware": shared_middleware,
    }

    db_scenario = {
        "name": "db-scenario",
        "description": (
            "管理数据库中的测试场景编排（create_test_scenario、add_scenario_step 等），"
            "用于平台 UI 场景功能，不是 HAT YAML 跨文件场景。"
        ),
        "system_prompt": f"""你是平台 DB 场景编排专家。

使用 create_test_scenario / add_scenario_step / execute_scenario 等工具管理数据库场景。
这与 HAT YAML 文件场景是不同体系，不要混用。

{_CONTEXT_HINT}
""",
        "tools": SCENARIO_TOOLS,
        "middleware": shared_middleware,
    }

    return [
        hat_planner,
        hat_generator,
        hat_scenario,
        hat_executor,
        hat_healer,
        db_scenario,
    ]
