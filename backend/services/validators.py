"""
validators.py — PRD 深度模式校验器矩阵

6 个校验器，每个接 Agent 产出，返回 Issue 列表。
Issue level: error(回退 Agent 重跑) / warn(标记继续)。
Issue action: retry_agent1|retry_agent3|mark|user_decide。

校验器触发位置：
  - Schema Validator: Agent1 之后（必填字段完整）
  - Scope Validator: Agent3 之后（范围蔓延检测）
  - Citation Validator: Agent3 之后（防幻觉，内容是否有依据）
  - Acceptance Validator: Agent3 之后（功能点是否都有验收标准）
  - Permission Validator: Agent3 之后（是否遗漏权限设计）
  - Risk Validator: Agent4 之后（是否缺失异常/性能/审计）
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _make_issue(level: str, field: str, message: str, action: str = 'mark') -> dict:
    """构造 Issue"""
    return {'level': level, 'field': field, 'message': message, 'action': action}


# ── Schema Validator（Agent1 之后）──


def validate_schema(agent1_out: dict) -> list[dict]:
    """必填字段是否完整

    error 级缺失 → retry_agent1
    """
    issues = []
    req = agent1_out.get('requirements', {}) or {}

    if not req.get('feature_name'):
        issues.append(_make_issue('error', 'requirements.feature_name', '缺少功能名称', 'retry_agent1'))
    if not req.get('problem'):
        issues.append(_make_issue('error', 'requirements.problem', '缺少问题陈述', 'retry_agent1'))
    if not req.get('solution_direction'):
        issues.append(_make_issue('error', 'requirements.solution_direction', '缺少解决方案方向', 'retry_agent1'))
    if not req.get('core_features'):
        issues.append(_make_issue('error', 'requirements.core_features', '缺少核心功能点', 'retry_agent1'))
    priorities = req.get('priorities', {}) or {}
    if not priorities.get('P0'):
        issues.append(_make_issue('error', 'requirements.priorities.P0', '缺少 P0 优先级功能', 'retry_agent1'))

    if not issues:
        logger.info('[PRDGen] V:Schema 通过')
    else:
        logger.warning(f'[PRDGen] V:Schema 失败 {len(issues)} 项')
    return issues


# ── Scope Validator（Agent3 之后，范围蔓延检测）──


def validate_scope(agent3_out: dict, user_input: str) -> list[dict]:
    """检测功能规格是否超出用户原始需求范围

    warn 级 → 标记超范围项，用户决定
    """
    issues = []
    user_text = user_input or ''
    features = agent3_out.get('features', []) or []
    user_keywords = {kw for kw in user_text if len(kw) >= 2}

    for feat in features:
        name = feat.get('name', '') if isinstance(feat, dict) else str(feat)
        # 简单策略：功能名与用户输入无共同词，疑似超范围
        feat_chars = set(name)
        if user_keywords and not (feat_chars & user_keywords):
            issues.append(_make_issue(
                'warn', f'features.{name}',
                f'功能「{name}」未在用户原始需求中提及，疑似范围蔓延',
                'user_decide',
            ))

    if not issues:
        logger.info('[PRDGen] V:Scope 通过')
    return issues


# ── Citation Validator（Agent3 之后，防幻觉）──


def validate_citation(agent3_out: dict) -> list[dict]:
    """内容是否有依据，防 LLM 臆造

    warn 级 → 标注无依据内容
    """
    issues = []
    features = agent3_out.get('features', []) or []
    stories = agent3_out.get('user_stories', []) or []

    for feat in features:
        if not isinstance(feat, dict):
            continue
        rationale = feat.get('rationale', '') or ''
        if rationale and ('可能' in rationale or '或许' in rationale or '猜测' in rationale):
            issues.append(_make_issue(
                'warn', f'features.{feat.get("name","")}',
                f'功能依据含不确定表述：「{rationale[:50]}」，建议核实',
                'mark',
            ))

    # 功能点无 rationale 字段视为无依据
    for feat in features:
        if isinstance(feat, dict) and not feat.get('rationale'):
            issues.append(_make_issue(
                'warn', f'features.{feat.get("name","")}',
                '功能缺少依据说明，可能为臆造',
                'mark',
            ))
            break  # 只报一次，避免刷屏

    if not issues:
        logger.info('[PRDGen] V:Citation 通过')
    return issues


# ── Acceptance Validator（Agent3 之后）──


def validate_acceptance(agent3_out: dict) -> list[dict]:
    """功能点是否都有验收标准

    error 级 → retry_agent3
    """
    issues = []
    features = agent3_out.get('features', []) or []
    stories = agent3_out.get('user_stories', []) or []

    for feat in features:
        if not isinstance(feat, dict):
            continue
        name = feat.get('name', '')
        criteria = feat.get('acceptance_criteria', []) or []
        if not criteria:
            issues.append(_make_issue(
                'error', f'features.{name}.acceptance_criteria',
                f'功能「{name}」缺少验收标准',
                'retry_agent3',
            ))

    if not stories:
        issues.append(_make_issue('error', 'user_stories', '缺少用户故事', 'retry_agent3'))

    if not issues:
        logger.info('[PRDGen] V:Acceptance 通过')
    else:
        logger.warning(f'[PRDGen] V:Acceptance 失败 {len(issues)} 项')
    return issues


# ── Permission Validator（Agent3 之后）──


def validate_permission(agent3_out: dict) -> list[dict]:
    """是否遗漏权限设计

    warn 级 → 提示补充（B 端平台权限必考虑）
    """
    issues = []
    text = ''
    features = agent3_out.get('features', []) or []
    for feat in features:
        if isinstance(feat, dict):
            text += feat.get('rationale', '') + feat.get('name', '')
    text += str(agent3_out.get('non_functional', '')) or ''

    # 检测权限相关关键词
    perm_keywords = ['权限', '角色', '审计', 'auth', 'permission', 'role']
    has_perm = any(kw in text for kw in perm_keywords)

    if not has_perm:
        issues.append(_make_issue(
            'warn', 'permission',
            '未检测到权限/角色/审计设计，B 端平台建议补充',
            'user_decide',
        ))

    if not issues:
        logger.info('[PRDGen] V:Permission 通过')
    return issues


# ── Risk Validator（Agent4 之后）──


def validate_risk(agent4_out: dict) -> list[dict]:
    """是否缺失异常处理/性能/审计

    warn 级 → 标记缺失项
    """
    issues = []
    prd = agent4_out.get('prd_markdown', '') or ''
    spec = agent4_out.get('spec', {}) or {}

    # 检测风险相关关键词
    risk_checks = {
        '异常处理': ['异常', '错误处理', 'Error', '失败', '回滚'],
        '性能指标': ['性能', '响应时间', 'p95', 'p99', '并发', 'qps'],
        '审计': ['审计', 'audit', '日志', '操作记录'],
    }

    all_text = prd
    nf = spec.get('nonFunctional', {}) if isinstance(spec.get('nonFunctional'), dict) else spec.get('non_functional', {})
    if isinstance(nf, dict):
        all_text += str(nf)

    for risk_type, keywords in risk_checks.items():
        if not any(kw in all_text for kw in keywords):
            issues.append(_make_issue(
                'warn', f'risk.{risk_type}',
                f'PRD 缺少「{risk_type}」相关设计',
                'mark',
            ))

    if not issues:
        logger.info('[PRDGen] V:Risk 通过')
    return issues


# ── 校验器矩阵入口 ──


def run_validators(stage: str, artifacts: dict, user_input: str = '') -> list[dict]:
    """按阶段运行校验器

    Args:
        stage: 'agent1' | 'agent3' | 'agent4'
        artifacts: 各 Agent 产出 {agent1: {...}, agent3: {...}, agent4: {...}}
        user_input: 用户原始需求（Scope Validator 用）

    Returns:
        所有 Issue 列表
    """
    all_issues = []
    if stage == 'agent1':
        all_issues.extend(validate_schema(artifacts.get('agent1', {})))
    elif stage == 'agent3':
        agent3 = artifacts.get('agent3', {})
        all_issues.extend(validate_scope(agent3, user_input))
        all_issues.extend(validate_citation(agent3))
        all_issues.extend(validate_acceptance(agent3))
        all_issues.extend(validate_permission(agent3))
    elif stage == 'agent4':
        all_issues.extend(validate_risk(artifacts.get('agent4', {})))
    return all_issues
