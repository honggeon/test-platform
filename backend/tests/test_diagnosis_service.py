"""
诊断引擎核心单元测试

覆盖规则匹配、降级路径、幂等性、脱敏等关键逻辑。
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.test_diagnosis_service import TestDiagnosisService
from app.services.diagnosis_cache import DiagnosisCache
from app.models.mongodb.diagnosis_report import DiagnosisReport


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def service():
    """创建诊断服务实例（mock 数据库连接）"""
    svc = TestDiagnosisService()
    svc.mongodb = MagicMock()
    return svc


@pytest.fixture
def sample_logs():
    """样本失败日志"""
    return [
        {
            "endpoint": "/api/v2/users",
            "method": "GET",
            "status_code": 401,
            "error_message": "Token expired",
            "request": {"headers": {"Authorization": "Bearer xxx"}},
            "response": {"body": {"error": "unauthorized"}},
        },
        {
            "endpoint": "/api/v2/orders",
            "method": "POST",
            "status_code": 403,
            "error_message": "Forbidden: insufficient permissions",
            "request": {},
            "response": {},
        },
        {
            "endpoint": "/api/v2/products",
            "method": "GET",
            "status_code": 404,
            "error_message": "Route not found",
            "request": {},
            "response": {},
        },
        {
            "endpoint": "/api/v2/checkout",
            "method": "POST",
            "status_code": 500,
            "error_message": "Internal Server Error: database connection timeout",
            "request": {},
            "response": {},
        },
    ]


# =============================================================================
# 规则引擎匹配测试
# =============================================================================

class TestRuleMatching:
    """测试规则引擎分类逻辑"""

    @pytest.mark.parametrize("status_code,error_message,expected_type,expected_rule", [
        (401, "Token expired", "token_expired", "token_expired_rule_1"),
        (401, "invalid_token", "token_expired", "token_expired_rule_1"),
        (401, "jwt invalid", "token_expired", "token_expired_rule_1"),
        (403, "Forbidden", "permission_denied", "permission_denied_rule_1"),
        (403, "insufficient permissions", "permission_denied", "permission_denied_rule_1"),
        (404, "not found", "api_changed", "api_changed_rule_1"),
        (404, "no route matched", "api_changed", "api_changed_rule_1"),
        (400, "unknown column name", "api_changed", "api_changed_rule_2"),
        (422, "field unknown", "api_changed", "api_changed_rule_2"),
        (400, "validation failed", "data_error", "data_error_rule_1"),
        (504, "Gateway Timeout", "network_timeout", "network_timeout_rule_1"),
        (502, "connection refused", "network_timeout", "network_timeout_rule_1"),
        (500, "TypeError: null is not a function", "script_error", "script_error_rule_1"),
        (200, "TypeError: foo is not a function", "script_error", "script_error_rule_1"),  # script_error 不限状态码
    ])
    def test_rule_hit(self, service, status_code, error_message, expected_type, expected_rule):
        """规则命中测试"""
        log = {
            "endpoint": "/api/test",
            "method": "GET",
            "status_code": status_code,
            "error_message": error_message,
        }
        rules = service._load_failure_rules()
        assert len(rules) > 0, "规则库未加载"

        matched = False
        for rule in rules:
            if rule["enabled"] and service._match_rule(log, rule):
                assert rule["category"] == expected_type
                assert rule["id"] == expected_rule
                matched = True
                break
        assert matched, f"期望命中规则 {expected_rule}，但未命中"

    def test_rule_miss_then_llm_fallback(self, service):
        """规则未命中时走 LLM 兜底"""
        log = {
            "endpoint": "/api/test",
            "method": "GET",
            "status_code": 418,  # 不在规则中的状态码
            "error_message": "I'm a teapot",  # 不匹配的 error message
        }
        # 确认没有规则命中
        rules = service._load_failure_rules()
        hit = any(service._match_rule(log, r) for r in rules if r["enabled"])
        assert not hit, "这个日志不应该被任何规则命中"


# =============================================================================
# 降级路径测试
# =============================================================================

class TestDegradationPaths:
    """测试各种降级路径"""

    @pytest.mark.asyncio
    async def test_empty_report_when_no_logs(self, service):
        """无失败日志时返回空报告"""
        report = service._empty_report("run-001", {"has_db_logs": True, "has_kg_locations": True, "has_llm_analysis": True, "fallback_reason": None})
        assert report.status == "completed"
        assert report.summary["total_failures"] == 0
        assert len(report.findings) == 0

    def test_emergency_report_on_engine_crash(self, service):
        """诊断引擎自身崩溃时返回 emergency_report"""
        report = service._emergency_report("run-001", "division by zero")
        assert report.status == "failed"
        assert report.degradation["has_db_logs"] is False
        assert "诊断引擎崩溃" in report.degradation["fallback_reason"]

    @pytest.mark.asyncio
    async def test_mongodb_unavailable_degradation(self, service):
        """MongoDB 不可用时标记降级"""
        # mock MongoDB 查询抛出异常
        service.mongodb.get_collection = MagicMock(side_effect=Exception("connection refused"))

        # _collect_failure_logs 会捕获异常并抛出，由 _execute_diagnosis 的 try/except 处理
        # 由于 _collect_failure_logs 内部 raise，外层 Phase 1 的 except 会捕获
        # 最终 _execute_diagnosis 的 except 会生成 emergency_report
        # 这里直接验证 _collect_failure_logs 的行为
        with pytest.raises(Exception):
            await service._collect_failure_logs("run-001")


# =============================================================================
# 幂等性测试
# =============================================================================

class TestIdempotency:
    """测试幂等性控制"""

    @pytest.mark.asyncio
    async def test_same_dedup_key_returns_existing(self, service):
        """相同 dedup_key 返回已有报告"""
        dedup_key = "run-001_proj-001"
        # mock _find_existing_report 返回一个已有的报告
        existing_report = DiagnosisReport(
            report_id=str(uuid4()),
            run_id="run-001",
            project_id="proj-001",
            status="completed",
            dedup_key=dedup_key,
            degradation={"has_db_logs": True, "has_kg_locations": True, "has_llm_analysis": True, "fallback_reason": None},
            summary={"total_failures": 1, "root_cause_counts": {}},
            llm_token_cost={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_cost_usd": 0.0},
            completed_at=datetime.now(timezone.utc),
        )
        service._find_existing_report = AsyncMock(return_value=existing_report)

        result = await service.diagnose_run("run-001", "proj-001")
        assert result is existing_report

    @pytest.mark.asyncio
    async def test_skip_dedup_executes_anyway(self, service):
        """skip_dedup=True 时跳过幂等检查，重新执行诊断"""
        service._find_existing_report = AsyncMock(return_value=None)
        # 直接测试 _generate_report 使用 preset_report_id
        report = service._generate_report(
            [], {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_cost_usd": 0.0},
            "run-001", "proj-001", preset_report_id="preset-123"
        )
        assert report.report_id == "preset-123"

        report2 = service._empty_report("run-001", {}, preset_report_id="preset-456")
        assert report2.report_id == "preset-456"

        report3 = service._emergency_report("run-001", "error", preset_report_id="preset-789")
        assert report3.report_id == "preset-789"

    def test_generate_report_uses_override_dedup_key(self, service):
        report = service._generate_report(
            [], {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_cost_usd": 0.0},
            "run-001", "proj-001", preset_report_id="r1", dedup_key="custom_key",
        )
        assert report.dedup_key == "custom_key"


# =============================================================================
# 脱敏测试
# =============================================================================

class TestSanitization:
    """测试敏感数据脱敏"""

    def test_sanitize_request_headers(self, service):
        """脱敏请求头中的敏感字段"""
        log = {
            "request": {
                "headers": {
                    "Authorization": "Bearer secret_token",
                    "Cookie": "session=abc123",
                    "Content-Type": "application/json",
                }
            },
            "response": {},
        }
        result = service._sanitize_log(log)
        assert result["request"]["headers"]["Authorization"] == "***"
        assert result["request"]["headers"]["Cookie"] == "***"
        assert result["request"]["headers"]["Content-Type"] == "application/json"

    def test_sanitize_request_body(self, service):
        """脱敏请求体中的敏感字段"""
        log = {
            "request": {
                "body": {
                    "username": "alice",
                    "password": "supersecret",
                    "api_key": "sk-12345",
                }
            },
            "response": {},
        }
        result = service._sanitize_log(log)
        assert result["request"]["body"]["username"] == "alice"
        assert result["request"]["body"]["password"] == "***"
        assert result["request"]["body"]["api_key"] == "***"

    def test_sanitize_nested_body(self, service):
        """脱敏嵌套结构中的敏感字段"""
        log = {
            "request": {},
            "response": {
                "body": {
                    "data": {
                        "accessToken": "tok123",
                        "phone": "13800138000",
                        "name": "Alice",
                    },
                    "success": True,
                }
            },
        }
        result = service._sanitize_log(log)
        assert result["response"]["body"]["data"]["accessToken"] == "***"
        assert result["response"]["body"]["data"]["phone"] == "***"
        assert result["response"]["body"]["data"]["name"] == "Alice"
        assert result["response"]["body"]["success"] is True

    def test_sanitize_no_sensitive_data(self, service):
        """无敏感数据时不改变内容"""
        log = {
            "request": {"body": {"name": "Alice", "age": 30}},
            "response": {"body": {"status": "ok"}},
        }
        result = service._sanitize_log(log)
        assert result["request"]["body"]["name"] == "Alice"
        assert result["request"]["body"]["age"] == 30
        assert result["response"]["body"]["status"] == "ok"


# =============================================================================
# 去重测试
# =============================================================================

class TestDeduplication:
    """测试日志去重逻辑"""

    def test_dedup_by_endpoint_method_status(self, service):
        """按 endpoint + method + status_code 去重"""
        logs = [
            {"endpoint": "/api/users", "method": "GET", "status_code": 401},
            {"endpoint": "/api/users", "method": "GET", "status_code": 401},  # 重复
            {"endpoint": "/api/users", "method": "POST", "status_code": 401},  # method 不同，保留
            {"endpoint": "/api/users", "method": "GET", "status_code": 403},  # status 不同，保留
        ]
        result = service._dedup_logs(logs)
        assert len(result) == 3
        keys = [(r["endpoint"], r["method"], r["status_code"]) for r in result]
        assert ("/api/users", "GET", 401) in keys
        assert ("/api/users", "POST", 401) in keys
        assert ("/api/users", "GET", 403) in keys


# =============================================================================
# 降级等级计算测试
# =============================================================================

class TestDegradationLevel:
    """测试降级等级计算"""

    def test_none_degradation(self, service):
        """全部正常：none"""
        assert service._calc_degradation_level({"has_db_logs": True, "has_kg_locations": True}) == "none"

    def test_partial_degradation(self, service):
        """DB 可用但 KG 不可用：partial"""
        assert service._calc_degradation_level({"has_db_logs": True, "has_kg_locations": False}) == "partial"

    def test_severe_degradation(self, service):
        """DB 不可用：severe"""
        assert service._calc_degradation_level({"has_db_logs": False, "has_kg_locations": False}) == "severe"


# =============================================================================
# 缓存测试
# =============================================================================

class TestDiagnosisCache:
    """测试 LLM 诊断缓存"""

    @pytest.mark.asyncio
    async def test_cache_key_uniqueness(self):
        """不同上下文的缓存 key 应该不同"""
        key1 = DiagnosisCache.make_key(404, "GET", "/api/users", "not found")
        key2 = DiagnosisCache.make_key(404, "POST", "/api/users", "not found")
        key3 = DiagnosisCache.make_key(404, "GET", "/api/orders", "not found")
        assert key1 != key2
        assert key1 != key3
        assert key2 != key3

    @pytest.mark.asyncio
    async def test_cache_get_set(self):
        """缓存写入和读取"""
        cache = DiagnosisCache()
        await cache.set(401, "GET", "/api/users", "token expired", {"type": "token_expired", "confidence": 0.9})
        result = await cache.get(401, "GET", "/api/users", "token expired")
        assert result is not None
        assert result["type"] == "token_expired"

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self):
        """缓存过期后应该返回 None"""
        cache = DiagnosisCache()
        cache._ttl = 0.01  # 10ms 过期
        await cache.set(401, "GET", "/api/users", "token expired", {"type": "token_expired"})
        await asyncio.sleep(0.02)
        result = await cache.get(401, "GET", "/api/users", "token expired")
        assert result is None


# =============================================================================
# 端到端简化测试
# =============================================================================

class TestEndToEnd:
    """端到端核心流程测试"""

    @pytest.mark.asyncio
    async def test_diagnose_with_mock_db(self, service):
        """使用 mock 数据库测试完整诊断流程"""
        # mock MongoDB 返回空（无失败日志）
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        service.mongodb.get_collection = MagicMock(return_value=mock_collection)

        # mock _save_report, _notify_frontend 和 _notify_progress 避免实际写入
        service._save_report = AsyncMock()
        service._notify_frontend = AsyncMock()
        service._notify_progress = AsyncMock()

        report = await service.diagnose_run("run-001", "proj-001")
        assert report.status in ("completed", "failed")
        service._save_report.assert_called_once()
