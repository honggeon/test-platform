"""
诊断引擎核心服务

日志分析 Agent 的核心诊断引擎，负责采集失败日志、分类失败模式、
KG 代码定位、生成修复建议并持久化诊断报告。
"""
"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

import asyncio
import hashlib
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4, UUID

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.database import MongoDB, async_session_factory
from app.models.diagnosis_report import DiagnosisReportPG
from app.models.mongodb.diagnosis_report import DiagnosisReport
from app.models.test_scenario import ScenarioStepResult
from app.agents.log_analysis.tools.kg_integration_tools import KGIntegrationTools
from app.services.diagnosis_cache import DiagnosisCache
from app.services.diagnosis_notification_service import manager as ws_manager

logger = logging.getLogger(__name__)


class TestDiagnosisService:
    KG_TIMEOUT = 3.0
    LLM_TIMEOUT = 10.0
    DB_TIMEOUT = 5.0
    KG_RETRY_MAX = 2
    KG_RETRY_DELAY = 0.5
    MAX_LLM_ANALYSIS = 10

    # 敏感数据脱敏配置
    SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key", "x-apikey", "token", "x-auth-token"}
    SENSITIVE_BODY_FIELDS = {
        "password", "secret", "token", "accessToken", "refreshToken",
        "creditCard", "phone", "idCard", "id_card", "ssn", "api_key", "apikey"
    }

    def __init__(self, mongodb=None, db_session=None, redis_client=None):
        self.mongodb = mongodb or MongoDB.get_database()
        self.db = db_session
        self.redis = redis_client
        self.cache = DiagnosisCache(redis_client)
        self._rules_cache = None
        self._rules_cache_ts = 0
        self._rules_ttl = 60

    async def diagnose_run(self, run_id: str, project_id: str, project_identifier: str = "", options: dict = None) -> DiagnosisReport:
        options = options or {}
        # 支持重新诊断（覆盖 dedup_key）
        override_key = options.get("override_dedup_key")
        skip_dedup = options.get("skip_dedup", False)
        preset_report_id = options.get("preset_report_id")
        dedup_key = override_key or f"{run_id}_{project_id}"
        # 1. 幂等检查（重新诊断或触发工具已创建记录时跳过）
        if not override_key and not skip_dedup:
            existing = await self._find_existing_report(dedup_key)
            if existing:
                return existing
        # 2. 分布式锁（可选）
        # 3. 执行诊断
        return await self._execute_diagnosis(run_id, project_id, project_identifier, options, preset_report_id)

    async def _execute_diagnosis(self, run_id, project_id, project_identifier, options, preset_report_id=None) -> DiagnosisReport:
        start_time = time.monotonic()
        degradation = {"has_db_logs": True, "has_kg_locations": True, "has_llm_analysis": True, "fallback_reason": None}
        llm_cost = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_cost_usd": 0.0}
        report = None

        try:
            # Phase 1: 采集失败日志（含脱敏）
            try:
                logs = await asyncio.wait_for(self._collect_failure_logs(run_id), timeout=self.DB_TIMEOUT)
            except (asyncio.TimeoutError, Exception) as e:
                logs = []
                degradation["has_db_logs"] = False
                degradation["fallback_reason"] = f"DB 查询失败: {str(e)}"

            # 脱敏处理
            logs = [self._sanitize_log(log) for log in logs]

            if not logs:
                logs = self._parse_from_test_output(options.get("test_output", ""))
                if not logs:
                    report = self._empty_report(run_id, degradation, preset_report_id)

            if report is None:
                # Phase 2: 分类失败模式
                classified = await self._classify_failures(logs)

                # Phase 3: KG 代码定位（批量并行）
                findings = []
                if degradation["has_db_logs"] and classified and project_identifier:
                    batch_size = 10
                    for batch_start in range(0, len(classified), batch_size):
                        batch = classified[batch_start:batch_start + batch_size]
                        try:
                            batch_locations = await asyncio.wait_for(
                                asyncio.gather(
                                    *[self._locate_in_code(f, project_identifier) for f in batch],
                                    return_exceptions=True
                                ),
                                timeout=self.KG_TIMEOUT + 2.0
                            )
                        except asyncio.TimeoutError as e:
                            batch_locations = [[] for _ in batch]
                            degradation["has_kg_locations"] = False
                            degradation["fallback_reason"] = f"KG 整批超时: {str(e)}"

                        for failure, locations in zip(batch, batch_locations):
                            if isinstance(locations, Exception):
                                locations = []
                                degradation["has_kg_locations"] = False
                            findings.append({**failure, "code_locations": locations})
                else:
                    for failure in classified:
                        findings.append({**failure, "code_locations": []})

                # Phase 4: 生成修复建议
                report = self._generate_report(findings, degradation, llm_cost, run_id, project_id, preset_report_id)

        except Exception as e:
            report = self._emergency_report(run_id, str(e), preset_report_id)

        # Phase 5: 持久化（空报告也需要保存以更新 analyzing 记录）
        if report is None:
            report = self._empty_report(run_id, degradation, preset_report_id)
        report.analysis_duration_ms = int((time.monotonic() - start_time) * 1000)
        try:
            await self._save_report(report)
        except Exception as e:
            logger.error(f"保存诊断报告失败: {e}")

        # Phase 6: 推送
        try:
            await self._notify_frontend(report)
        except Exception as e:
            logger.error(f"推送诊断报告失败: {e}")

        return report

    async def _collect_failure_logs(self, run_id: str) -> list[dict]:
        logs = []
        # 1. MongoDB api_test_logs
        try:
            collection = self.mongodb.get_collection("api_test_logs")
            cursor = collection.find({
                "$or": [
                    {"test_run_id": run_id},
                    {"test_run_id": UUID(run_id) if self._is_uuid(run_id) else run_id}
                ],
                "status": {"$in": ["failed", "error"]}
            }).limit(100)
            mongo_logs = await cursor.to_list(length=100)
            for doc in mongo_logs:
                logs.append(self._normalize_mongo_log(doc))
        except Exception as e:
            logger.warning(f"MongoDB 查询失败: {e}")
            raise

        # 2. PG scenario_step_results
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(ScenarioStepResult).where(
                        ScenarioStepResult.run_id == UUID(run_id),
                        ScenarioStepResult.status.in_(["failed", "error"])
                    )
                )
                pg_logs = result.scalars().all()
                for row in pg_logs:
                    logs.append(self._normalize_pg_log(row))
        except Exception as e:
            logger.warning(f"PG 查询失败: {e}")
            raise

        return self._dedup_logs(logs)

    def _normalize_mongo_log(self, doc: dict) -> dict:
        return {
            "log_id": str(doc.get("_id", "")),
            "source": "mongodb",
            "endpoint": doc.get("endpoint", ""),
            "method": doc.get("method", ""),
            "status_code": doc.get("status") or doc.get("status_code", 0),
            "error_message": self._extract_error(doc.get("error", {})) or "",
            "request": doc.get("request", {}),
            "response": doc.get("response", {}),
        }

    def _normalize_pg_log(self, row) -> dict:
        return {
            "log_id": str(row.id),
            "source": "postgresql",
            "endpoint": "",
            "method": "",
            "status_code": row.response_data.get("status", 0) if row.response_data else 0,
            "error_message": row.error_message or "",
            "request": row.request_data or {},
            "response": row.response_data or {},
        }

    def _sanitize_log(self, log: dict) -> dict:
        """对日志中的敏感数据进行脱敏处理"""
        sanitized = dict(log)

        def _sanitize_dict(data: dict, sensitive_keys: set, placeholder: str = "***") -> dict:
            if not isinstance(data, dict):
                return data
            result = {}
            for key, value in data.items():
                low_key = key.lower()
                if low_key in sensitive_keys or key in sensitive_keys:
                    result[key] = placeholder
                elif isinstance(value, dict):
                    result[key] = _sanitize_dict(value, sensitive_keys, placeholder)
                elif isinstance(value, list):
                    result[key] = [
                        _sanitize_dict(item, sensitive_keys, placeholder) if isinstance(item, dict) else item
                        for item in value
                    ]
                else:
                    result[key] = value
            return result

        # 脱敏 request headers
        request = sanitized.get("request", {})
        if isinstance(request, dict):
            headers = request.get("headers", {})
            if isinstance(headers, dict):
                request["headers"] = _sanitize_dict(headers, self.SENSITIVE_HEADERS)
            body = request.get("body", {})
            if isinstance(body, dict):
                request["body"] = _sanitize_dict(body, self.SENSITIVE_BODY_FIELDS)

        # 脱敏 response headers / body
        response = sanitized.get("response", {})
        if isinstance(response, dict):
            headers = response.get("headers", {})
            if isinstance(headers, dict):
                response["headers"] = _sanitize_dict(headers, self.SENSITIVE_HEADERS)
            body = response.get("body", {})
            if isinstance(body, dict):
                response["body"] = _sanitize_dict(body, self.SENSITIVE_BODY_FIELDS)

        return sanitized

    def _extract_error(self, error: dict) -> str:
        if isinstance(error, str):
            return error
        return error.get("message", "") or error.get("detail", "")

    def _dedup_logs(self, logs: list[dict]) -> list[dict]:
        seen = set()
        deduped = []
        for log in logs:
            key = (log.get("endpoint", ""), log.get("method", ""), str(log.get("status_code", "")))
            if key not in seen:
                seen.add(key)
                deduped.append(log)
        return deduped

    async def _classify_failures(self, logs: list[dict]) -> list[dict]:
        rules = self._load_failure_rules()
        results = []
        llm_candidates = []

        for log in logs:
            matched = False
            for rule in rules:
                if rule.get("enabled", True) and self._match_rule(log, rule):
                    results.append({
                        "log": log,
                        "type": rule["category"],
                        "confidence": rule["confidence"],
                        "classifier": "rule",
                        "matching_rule": rule["id"],
                        "llm_cache_hit": False,
                    })
                    matched = True
                    break
            if not matched:
                llm_candidates.append(log)

        # LLM 兜底
        if llm_candidates:
            llm_results = await self._llm_classify(llm_candidates)
            results.extend(llm_results)

        return self._merge_with_logs(results, logs)

    def _match_rule(self, log: dict, rule: dict) -> bool:
        status_ok = True
        sc_list = rule.get("conditions", {}).get("status_code", [])
        if sc_list and sc_list != ["*"]:
            log_status = str(log.get("status_code", ""))
            status_ok = log_status in [str(s) for s in sc_list]

        error_ok = False
        conditions = rule.get("conditions", {})
        # 兼容两种字段名: error_patterns / error_message_patterns
        patterns = conditions.get("error_patterns") or conditions.get("error_message_patterns", [])
        if not patterns:
            error_ok = True
        else:
            log_error = str(log.get("error_message", ""))
            for pat in patterns:
                if re.search(pat, log_error, re.IGNORECASE):
                    error_ok = True
                    break
        return status_ok and error_ok

    def _load_failure_rules(self) -> list[dict]:
        now = time.time()
        if self._rules_cache and (now - self._rules_cache_ts) < self._rules_ttl:
            return self._rules_cache

        rules_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "failure_rules.yaml")
        rules_path = os.path.abspath(rules_path)
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            rules = sorted(data.get("rules", []), key=lambda r: r.get("priority", 0), reverse=True)
            self._rules_cache = rules
            self._rules_cache_ts = now
            return rules
        except Exception as e:
            logger.error(f"加载规则库失败: {e}")
            return []

    async def _llm_classify(self, logs: list[dict]) -> list[dict]:
        # 分层抽样 + LLM 兜底
        # 简化实现：先检查缓存，未命中时按关键词简单分类
        # 实际生产环境应调用 LLM
        results = []
        for log in logs:
            # 检查缓存
            cached = await self.cache.get(
                log.get("status_code", 0),
                log.get("method", ""),
                log.get("endpoint", ""),
                log.get("error_message", "")
            )
            if cached:
                results.append({
                    "log": log,
                    "type": cached.get("type", "unknown"),
                    "confidence": cached.get("confidence", 0.5),
                    "classifier": "llm",
                    "matching_rule": None,
                    "llm_cache_hit": True,
                })
                continue

            # 未命中则按关键词简单分类（避免实际 LLM 调用使服务变重）
            # 实际生产环境应调用 LLM
            msg = str(log.get("error_message", "")).lower()
            if "token" in msg or "unauthorized" in msg or "jwt" in msg:
                results.append({"log": log, "type": "token_expired", "confidence": 0.7, "classifier": "llm", "matching_rule": None, "llm_cache_hit": False})
            elif "forbidden" in msg or "permission" in msg:
                results.append({"log": log, "type": "permission_denied", "confidence": 0.7, "classifier": "llm", "matching_rule": None, "llm_cache_hit": False})
            elif "not found" in msg or "no route" in msg:
                results.append({"log": log, "type": "api_changed", "confidence": 0.7, "classifier": "llm", "matching_rule": None, "llm_cache_hit": False})
            elif "timeout" in msg or "refused" in msg:
                results.append({"log": log, "type": "network_timeout", "confidence": 0.7, "classifier": "llm", "matching_rule": None, "llm_cache_hit": False})
            elif "typeerror" in msg or "referenceerror" in msg:
                results.append({"log": log, "type": "script_error", "confidence": 0.7, "classifier": "llm", "matching_rule": None, "llm_cache_hit": False})
            else:
                results.append({"log": log, "type": "unknown", "confidence": 0.5, "classifier": "llm", "matching_rule": None, "llm_cache_hit": False})
        return results

    def _merge_with_logs(self, classified: list[dict], logs: list[dict]) -> list[dict]:
        return classified

    async def _locate_in_code(self, failure: dict, project_identifier: str) -> list[dict]:
        """多策略并行级联定位"""
        if not project_identifier:
            return []
        kg = KGIntegrationTools(project_identifier)
        endpoint = failure.get("log", {}).get("endpoint", "")
        error_msg = failure.get("log", {}).get("error_message", "")
        root_cause = failure.get("type", "")

        tasks = []
        strategies = {}

        # 策略 1: 从 Endpoint 路径定位路由层
        path_segments = endpoint.strip("/").split("/")
        for seg in path_segments:
            if seg and seg not in ("api", "v1", "v2"):
                tasks.append(kg.search_code(seg))
                strategies[len(tasks) - 1] = "route_layer"

        # 策略 2: 从错误关键词定位逻辑层
        symbols = re.findall(r'[A-Za-z_]\w+', error_msg)
        for sym in symbols[:3]:
            tasks.append(kg.get_symbol_context(sym))
            strategies[len(tasks) - 1] = "logic_layer"

        # 策略 3: 从根因类型定位中间件层
        keyword_map = {
            "token_expired": ("middleware", "auth", "token"),
            "permission_denied": ("permission", "role", "rbac"),
            "api_changed": (*path_segments[-2:],),
        }
        if root_cause in keyword_map:
            # 将关键词拼接为查询串
            query_str = " ".join([str(k) for k in keyword_map[root_cause] if k])
            tasks.append(kg.search_code(query_str))
            strategies[len(tasks) - 1] = "middleware_layer"

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        locations = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                continue
            if isinstance(result, dict):
                if result.get("matches") or result.get("found"):
                    locations.append({
                        "strategy": strategies.get(idx, "unknown"),
                        "result": result,
                        "confidence": 0.8,
                    })

        # 策略 4: 影响分析（串行，依赖前面结果）
        if locations:
            # 简化处理：对第一个定位结果做影响分析
            first_result = locations[0].get("result", {})
            if isinstance(first_result, dict) and first_result.get("matches"):
                matches = first_result["matches"]
                if matches and isinstance(matches[0], str):
                    # 提取符号名尝试影响分析
                    symbol_match = re.search(r'\]\s+(\w+)', matches[0])
                    if symbol_match:
                        try:
                            impact = await kg.impact_analysis(symbol_match.group(1), direction="both")
                            if impact.get("report"):
                                locations.append({
                                    "strategy": "impact_analysis",
                                    "result": impact,
                                    "confidence": 0.6,
                                })
                        except Exception:
                            pass

        return locations

    def _generate_report(self, findings, degradation, llm_cost, run_id, project_id, preset_report_id=None) -> DiagnosisReport:
        root_cause_counts = {
            "token_expired": 0, "permission_denied": 0, "api_changed": 0,
            "data_error": 0, "network_timeout": 0, "script_error": 0, "unknown": 0
        }
        for f in findings:
            t = f.get("type", "unknown")
            if t in root_cause_counts:
                root_cause_counts[t] += 1
            else:
                root_cause_counts["unknown"] += 1

        return DiagnosisReport(
            report_id=preset_report_id or str(uuid4()),
            run_id=run_id,
            project_id=project_id,
            status="completed",
            dedup_key=f"{run_id}_{project_id}",
            source_type="api_test",
            test_type="single",
            degradation=degradation,
            summary={"total_failures": len(findings), "root_cause_counts": root_cause_counts},
            findings=[self._finding_to_dict(f) for f in findings],
            llm_token_cost=llm_cost,
            completed_at=datetime.now(timezone.utc),
        )

    def _finding_to_dict(self, finding: dict) -> dict:
        log = finding.get("log", {})
        return {
            "failure_id": str(uuid4()),
            "endpoint": log.get("endpoint", ""),
            "method": log.get("method", ""),
            "status_code": log.get("status_code", 0),
            "error_message": log.get("error_message", ""),
            "root_cause_type": finding.get("type", "unknown"),
            "root_cause_detail": "",
            "classifier": finding.get("classifier", "rule"),
            "matching_rule": finding.get("matching_rule"),
            "code_locations": finding.get("code_locations", []),
            "affects_apis": [],
            "fix_suggestions": [],
            "llm_cache_hit": finding.get("llm_cache_hit", False),
        }

    async def _save_report(self, report: DiagnosisReport):
        # PG 优先策略（upsert：存在则更新，不存在则插入）
        try:
            async with async_session_factory() as session:
                # 先查询是否已存在（触发工具可能已创建 analyzing 记录）
                result = await session.execute(
                    select(DiagnosisReportPG).where(DiagnosisReportPG.dedup_key == report.dedup_key)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    # 更新已有记录
                    existing.status = report.status
                    existing.summary_json = report.summary
                    existing.error_count = report.summary.get("total_failures", 0)
                    existing.degradation_level = self._calc_degradation_level(report.degradation)
                    existing.llm_tokens_used = report.llm_token_cost.get("total_tokens", 0)
                    existing.analysis_duration_ms = report.analysis_duration_ms
                    existing.mongo_id = report.report_id
                    existing.completed_at = report.completed_at
                    await session.commit()
                else:
                    # 新建记录
                    pg_report = DiagnosisReportPG(
                        id=UUID(report.report_id),
                        project_id=UUID(report.project_id) if report.project_id else None,
                        run_id=UUID(report.run_id),
                        dedup_key=report.dedup_key,
                        report_type=report.source_type,
                        status=report.status,
                        summary_json=report.summary,
                        source_type=report.source_type,
                        error_count=report.summary.get("total_failures", 0),
                        degradation_level=self._calc_degradation_level(report.degradation),
                        llm_tokens_used=report.llm_token_cost.get("total_tokens", 0),
                        analysis_duration_ms=report.analysis_duration_ms,
                        mongo_id=report.report_id,
                        completed_at=report.completed_at,
                    )
                    session.add(pg_report)
                    await session.commit()
        except Exception as e:
            logger.error(f"PG 写入失败，诊断报告丢弃: {e}")
            raise

        # MongoDB（upsert）
        try:
            collection = self.mongodb.get_collection("diagnosis_reports")
            await collection.replace_one(
                {"report_id": report.report_id},
                report.to_document(),
                upsert=True,
            )
        except Exception as e:
            logger.error(f"MongoDB 写入失败，启动补偿: {e}")
            asyncio.create_task(self._compensate_mongo(report))

    async def _compensate_mongo(self, report: DiagnosisReport, retries=3):
        for attempt in range(retries):
            try:
                await asyncio.sleep(30)
                collection = self.mongodb.get_collection("diagnosis_reports")
                await collection.insert_one(report.to_document())
                return
            except Exception:
                if attempt == retries - 1:
                    logger.error(f"MongoDB 补偿写入最终失败, report_id={report.report_id}")

    async def _find_existing_report(self, dedup_key: str) -> Optional[DiagnosisReport]:
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(DiagnosisReportPG).where(DiagnosisReportPG.dedup_key == dedup_key)
                )
                pg_report = result.scalar_one_or_none()
                if pg_report:
                    return await self._load_full_report(pg_report)
        except Exception as e:
            logger.warning(f"查询已有报告失败: {e}")
        return None

    async def _load_full_report(self, pg_report: DiagnosisReportPG) -> DiagnosisReport:
        try:
            collection = self.mongodb.get_collection("diagnosis_reports")
            doc = await collection.find_one({"report_id": pg_report.mongo_id})
            if doc:
                return DiagnosisReport(**doc)
        except Exception as e:
            logger.warning(f"从 MongoDB 加载完整报告失败: {e}")
        # 从 PG 重建概要
        return DiagnosisReport(
            report_id=str(pg_report.id),
            run_id=str(pg_report.run_id),
            project_id=str(pg_report.project_id) if pg_report.project_id else "",
            status=pg_report.status,
            dedup_key=pg_report.dedup_key,
            summary=pg_report.summary_json or {},
            findings=[],
            degradation={},
            llm_token_cost={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_cost_usd": 0.0},
            completed_at=pg_report.completed_at or datetime.now(timezone.utc),
        )

    async def _notify_frontend(self, report: DiagnosisReport):
        await ws_manager.send_completed(
            report.project_id,
            {
                "type": "diagnosis_completed",
                "report_id": report.report_id,
                "status": report.status,
                "summary": report.summary,
                "degradation": report.degradation,
            }
        )

    def _empty_report(self, run_id: str, degradation: dict, preset_report_id=None) -> DiagnosisReport:
        return DiagnosisReport(
            report_id=preset_report_id or str(uuid4()),
            run_id=run_id,
            project_id="",
            status="completed",
            dedup_key=run_id,
            degradation=degradation,
            summary={"total_failures": 0, "root_cause_counts": {}},
            findings=[],
            llm_token_cost={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_cost_usd": 0.0},
            completed_at=datetime.now(timezone.utc),
        )

    def _emergency_report(self, run_id: str, error: str, preset_report_id=None) -> DiagnosisReport:
        return DiagnosisReport(
            report_id=preset_report_id or str(uuid4()),
            run_id=run_id,
            project_id="",
            status="failed",
            dedup_key=run_id,
            degradation={"has_db_logs": False, "has_kg_locations": False, "has_llm_analysis": False, "fallback_reason": f"诊断引擎崩溃: {error[:200]}"},
            summary={"total_failures": 0, "root_cause_counts": {}},
            findings=[],
            llm_token_cost={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_cost_usd": 0.0},
            completed_at=datetime.now(timezone.utc),
        )

    def _calc_degradation_level(self, degradation: dict) -> str:
        if degradation.get("has_db_logs") and degradation.get("has_kg_locations"):
            return "none"
        if degradation.get("has_db_logs"):
            return "partial"
        return "severe"

    def _parse_from_test_output(self, test_output: str) -> list[dict]:
        # 从测试输出文本解析失败信息（简化实现）
        logs = []
        # 简单正则匹配常见的 HTTP 错误
        pattern = re.compile(r'(GET|POST|PUT|DELETE|PATCH)\s+(/\S+)\s+.*?\[(\d{3})\].*?(error|fail|timeout)', re.IGNORECASE)
        for m in pattern.finditer(test_output):
            logs.append({
                "endpoint": m.group(2),
                "method": m.group(1).upper(),
                "status_code": int(m.group(3)),
                "error_message": test_output[m.start():m.start()+200],
            })
        return logs

    @staticmethod
    def _is_uuid(val: str) -> bool:
        try:
            UUID(val)
            return True
        except ValueError:
            return False

    # =====================================================================
    # 规则统计
    # =====================================================================

    async def get_rule_stats(self, project_id: str, days: int = 7) -> dict:
        """
        统计规则引擎命中率和 LLM 兜底率

        通过聚合最近 N 天的诊断报告中的 findings 字段计算统计信息。
        """
        from datetime import timedelta

        try:
            collection = self.mongodb.get_collection("diagnosis_reports")
            since = datetime.now(timezone.utc) - timedelta(days=days)
            cursor = collection.find({
                "project_id": project_id,
                "status": {"$in": ["completed", "failed"]},
                "created_at": {"$gte": since},
            })
            reports = await cursor.to_list(length=1000)
        except Exception as e:
            logger.warning(f"统计查询失败: {e}")
            return {"total_rules": 0, "hit_counts": {}, "llm_fallback_count": 0, "hit_rate": 0.0}

        rule_hits = {}
        llm_fallback = 0
        total_classified = 0

        for report in reports:
            for finding in report.get("findings", []):
                total_classified += 1
                classifier = finding.get("classifier", "")
                if classifier == "rule":
                    rule_id = finding.get("matching_rule", "unknown")
                    rule_hits[rule_id] = rule_hits.get(rule_id, 0) + 1
                elif classifier == "llm":
                    llm_fallback += 1

        total_hits = sum(rule_hits.values())
        hit_rate = total_hits / total_classified if total_classified > 0 else 0.0

        return {
            "total_rules": len(self._load_failure_rules()),
            "hit_counts": rule_hits,
            "llm_fallback_count": llm_fallback,
            "total_classified": total_classified,
            "hit_rate": round(hit_rate, 4),
            "period_days": days,
        }

    # =====================================================================
    # 数据清理
    # =====================================================================

    async def cleanup_old_reports(self, days: int = 90) -> int:
        """
        清理指定天数前的诊断报告

        Returns:
            删除的记录数
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        deleted = 0

        # 清理 MongoDB
        try:
            collection = self.mongodb.get_collection("diagnosis_reports")
            result = await collection.delete_many({"created_at": {"$lt": cutoff}})
            deleted += result.deleted_count
            logger.info(f"MongoDB 清理完成: 删除 {result.deleted_count} 条过期诊断报告")
        except Exception as e:
            logger.warning(f"MongoDB 清理失败: {e}")

        # 清理 PG
        try:
            async with async_session_factory() as session:
                from sqlalchemy import delete
                result = await session.execute(
                    delete(DiagnosisReportPG).where(DiagnosisReportPG.created_at < cutoff)
                )
                await session.commit()
                deleted += result.rowcount
                logger.info(f"PG 清理完成: 删除 {result.rowcount} 条过期诊断报告")
        except Exception as e:
            logger.warning(f"PG 清理失败: {e}")

        return deleted

    async def ensure_ttl_index(self):
        """确保 MongoDB TTL 索引已创建（应用启动时调用）"""
        try:
            collection = self.mongodb.get_collection("diagnosis_reports")
            # TTL 索引: 90 天后自动删除
            await collection.create_index(
                "created_at",
                expireAfterSeconds=90 * 24 * 3600,
                name="diagnosis_reports_ttl",
            )
            logger.info("MongoDB TTL 索引已创建/确认")
        except Exception as e:
            logger.warning(f"创建 TTL 索引失败: {e}")
