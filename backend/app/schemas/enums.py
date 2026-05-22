"""
系统枚举值定义

基于 BrowserStack Test Management API 的枚举值定义
参考: https://www.browserstack.com/docs/test-management/api-reference/enums
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""


from enum import Enum


class Priority(str, Enum):
    """
    测试用例优先级
    
    用于标识测试用例的重要程度和执行优先顺序
    """
    LOW = "low"           # 低优先级
    MEDIUM = "medium"     # 中优先级
    HIGH = "high"         # 高优先级
    CRITICAL = "critical" # 关键优先级


class TestCaseState(str, Enum):
    """
    测试用例状态

    基于测试用例生命周期的完整状态定义

    设计阶段状态：
    - new: 新建 - 用例刚创建，尚未评审
    - review_pending: 待评审 - 等待团队评审
    - reviewed: 已评审 - 评审完成，可准备执行

    执行阶段状态：
    - not_run: 未执行 - 尚未执行过
    - passed: 通过 - 执行结果符合预期
    - failed: 失败 - 执行结果与预期不符
    - blocked: 阻塞 - 因依赖问题无法执行
    - skipped: 跳过 - 因特定原因跳过执行
    """
    # 设计阶段
    NEW = "new"                           # 新建
    REVIEW_PENDING = "review_pending"     # 待评审
    REVIEWED = "reviewed"                 # 已评审

    # 执行阶段
    NOT_RUN = "not_run"                   # 未执行
    PASSED = "passed"                     # 通过
    FAILED = "failed"                     # 失败
    BLOCKED = "blocked"                   # 阻塞
    SKIPPED = "skipped"                   # 跳过


class TestCaseType(str, Enum):
    """
    测试用例类型
    
    用于分类测试用例的测试类型
    """
    ACCEPTANCE = "acceptance"       # 验收测试
    ACCESSIBILITY = "accessibility" # 可访问性测试
    COMPATIBILITY = "compatibility" # 兼容性测试
    DESTRUCTIVE = "destructive"     # 破坏性测试
    FUNCTIONAL = "functional"       # 功能测试
    OTHER = "other"                 # 其他类型
    PERFORMANCE = "performance"     # 性能测试
    REGRESSION = "regression"       # 回归测试
    SECURITY = "security"           # 安全测试
    SMOKE_SANITY = "smoke_sanity"   # 冒烟和健全性测试
    USABILITY = "usability"         # 可用性测试


class HTTPStatusCode(int, Enum):
    """
    HTTP 状态码
    
    API 响应使用的标准 HTTP 状态码
    参考: https://www.browserstack.com/docs/test-management/api-reference/status-code
    """
    OK = 200                    # 请求成功
    CREATED = 201               # 资源创建成功
    NO_CONTENT = 204            # 无内容（删除成功）
    BAD_REQUEST = 400           # 请求格式错误
    UNAUTHORIZED = 401          # 未授权 - 无效的访问凭证
    FORBIDDEN = 403             # 禁止访问
    NOT_FOUND = 404             # 资源未找到
    UNPROCESSABLE_ENTITY = 422  # 请求格式正确但语义错误
    TOO_MANY_REQUESTS = 429     # 请求过多 - 超出速率限制
    INTERNAL_SERVER_ERROR = 500 # 服务器内部错误


class SortOrder(str, Enum):
    """排序顺序"""
    ASC = "asc"   # 升序
    DESC = "desc" # 降序


class IssueType(str, Enum):
    """
    关联问题类型

    用于标识测试用例关联的外部问题类型
    """
    JIRA = "jira"           # Jira 问题
    GITHUB = "github"       # GitHub Issue
    GITLAB = "gitlab"       # GitLab Issue
    AZURE = "azure"         # Azure DevOps
    OTHER = "other"         # 其他类型


class TestCaseTemplate(str, Enum):
    """
    测试用例模板类型

    用于区分普通测试用例和 BDD 测试用例
    """
    TEST_CASE = "test_case"       # 普通测试用例
    TEST_CASE_BDD = "test_case_bdd"  # BDD 测试用例


class AutomationStatus(str, Enum):
    """
    自动化状态

    用于标识测试用例的自动化程度
    """
    NOT_AUTOMATED = "not_automated"   # 未自动化
    AUTOMATED = "automated"           # 已自动化
    IN_PROGRESS = "in_progress"       # 自动化进行中
    OBSOLETE = "obsolete"             # 自动化已过时


class BulkEditOperation(str, Enum):
    """
    批量编辑操作符

    用于批量编辑测试用例时指定字段的处理方式
    """
    IGNORE = "ignore"     # 保持现有值不变
    REPLACE = "replace"   # 用提供的值覆盖当前值
    ADD = "add"           # 将提供的值追加到现有列表（多值字段）
    REMOVE = "remove"     # 从现有列表中移除指定的值（多值字段）


class ExportStatus(str, Enum):
    """
    导出任务状态

    用于标识 BDD 测试用例导出任务的状态
    """
    PENDING = "pending"       # 等待处理
    PROCESSING = "processing" # 处理中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败


class TestRunState(str, Enum):
    """
    测试运行状态

    用于标识测试运行的执行状态
    参考: https://www.browserstack.com/docs/test-management/api-reference/test-runs
    """
    NEW_RUN = "new_run"           # 新建运行
    IN_PROGRESS = "in_progress"   # 进行中
    UNDER_REVIEW = "under_review" # 审核中
    REJECTED = "rejected"         # 已拒绝
    DONE = "done"                 # 已完成
    CLOSED = "closed"             # 已关闭


class TestRunActiveState(str, Enum):
    """
    测试运行活跃状态

    用于标识测试运行是否处于活跃状态
    """
    ACTIVE = "active"   # 活跃状态
    CLOSED = "closed"   # 已关闭


class TestResultStatus(str, Enum):
    """
    测试结果状态

    用于标识单个测试用例在测试运行中的执行结果
    参考: https://www.browserstack.com/docs/test-management/api-reference/test-results

    官方 API 支持的状态值:
    - passed: 测试通过
    - failed: 测试失败
    - skipped: 测试跳过
    - blocked: 测试被阻塞
    - not_executed: 未执行
    """
    PASSED = "passed"             # 通过
    FAILED = "failed"             # 失败
    SKIPPED = "skipped"           # 跳过
    BLOCKED = "blocked"           # 阻塞
    NOT_EXECUTED = "not_executed" # 未执行


class TestPlanStatus(str, Enum):
    """
    测试计划状态

    用于标识测试计划的当前状态
    参考: https://www.browserstack.com/docs/test-management/api-reference/test-plans
    """
    DRAFT = "draft"           # 草稿
    ACTIVE = "active"         # 活跃
    COMPLETED = "completed"   # 已完成
    ARCHIVED = "archived"     # 已归档


class TestPlanActiveState(str, Enum):
    """
    测试计划活跃状态

    用于标识测试计划是否处于活跃状态
    """
    ACTIVE = "active"   # 活跃状态
    CLOSED = "closed"   # 已关闭
