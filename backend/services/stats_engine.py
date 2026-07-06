"""
迭代数据统计引擎

移植自桌面 iteration-stats skill 的 stats_from_xlsx.py 核心逻辑。
读取 RDC 导出的 xlsx 文件，逐行统计各项目的工程/AIcoding/SDD/端到端数据。

统计规则：
1. 总需求数 = 所有行数
2. 算法工程需求 = 完全排期 + 有工程工时 + 有负责人
3. AIcoding需求数 = 算法工程需求中标签匹配 AICoding 关键词
4. SDD需求数 = 算法工程需求中标签匹配 SDD 关键词
5. 端到端需求数 = 算法工程需求中标签匹配 端到端 关键词
6. AICoding占比 = AIcoding / 工程 (分母=0则0)
7. SDD占比 = SDD / AIcoding (分母=0则0)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── 标签匹配关键词 ──
AICODING_KEYWORDS = ["端到端", "aicoding", "ai coding", "sdd", "tdd"]
SDD_KEYWORDS = ["sdd"]
ENDTOEND_KEYWORDS = ["端到端"]

# 负责人列名
RESPONSIBLE_COLS = ["产品负责人", "技术负责人", "测试负责人", "需求第一责任人"]


def parse_project_xlsx(filepath: str) -> pd.DataFrame:
    """读取并预处理 xlsx 文件"""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")

    df = pd.read_excel(path)
    logger.info(f"读取 {path.name}: {len(df)} 条数据")

    # 标准化列名（去除空格）
    df.columns = [str(c).strip() for c in df.columns]
    return df


def find_engineering_columns(df: pd.DataFrame) -> List[str]:
    """查找工程工时列：列名含"工程"且含"估时"或"工时" """
    cols = []
    for col in df.columns:
        cl = col.lower()
        if "工程" in cl and ("估时" in cl or "工时" in cl):
            cols.append(col)
    return cols


def has_responsible(row) -> bool:
    """检查是否至少有一个负责人有值"""
    for col in RESPONSIBLE_COLS:
        if col in row.index and pd.notna(row[col]) and str(row[col]).strip():
            return True
    return False


def has_engineering_hours(row, engineering_cols: List[str]) -> bool:
    """检查工程工时列是否有正值"""
    for col in engineering_cols:
        if col in row.index and pd.notna(row[col]):
            try:
                if float(row[col]) > 0:
                    return True
            except (ValueError, TypeError):
                pass
    return False


def match_tags(tags_val, keywords: List[str]) -> bool:
    """检查标签值是否匹配任意关键词"""
    if pd.isna(tags_val):
        return False
    tags_str = str(tags_val).lower()
    return any(kw.lower() in tags_str for kw in keywords)


def extract_project_name(df: pd.DataFrame) -> Optional[str]:
    """从数据中提取项目名称（从'所属迭代'列取第一个值）"""
    if "所属迭代" in df.columns:
        vals = df["所属迭代"].dropna().unique()
        if len(vals) > 0:
            return str(vals[0])
    return None


def calculate_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """计算单项目的统计数据

    Returns:
        dict: {
            "total_requirements": int,
            "engineering_requirements": int,
            "aicoding_count": int,
            "sdd_count": int,
            "endtoend_count": int,
            "aicoding_ratio": float,   # 百分比保留2位小数
            "sdd_ratio": float,
            "project_name": str|None,
            "details": [...]   # 详细行记录
        }
    """
    engineering_cols = find_engineering_columns(df)
    logger.info(f"找到工程工时列: {len(engineering_cols)} 个 -> {engineering_cols}")
    logger.info(f"所有列名: {list(df.columns)}")

    # 查找标签列 — 扩展匹配范围
    tag_col = None
    for col in df.columns:
        cl = str(col).lower()
        if any(kw in cl for kw in ["标签", "tag", "分类", "类型"]):
            tag_col = col
            break
    logger.info(f"匹配到的标签列: {tag_col}")

    stats = {
        "total_requirements": 0,
        "engineering_requirements": 0,
        "aicoding_count": 0,
        "sdd_count": 0,
        "endtoend_count": 0,
        "project_name": extract_project_name(df),
        "details": [],
    }

    for _, row in df.iterrows():
        stats["total_requirements"] += 1

        # 排期结果
        schedule_result = row.get("排期结果", "")
        is_fully_scheduled = pd.notna(schedule_result) and "完全排期" in str(schedule_result)

        if not is_fully_scheduled:
            continue

        # 负责人 + 工程工时
        if not has_responsible(row):
            continue
        if not has_engineering_hours(row, engineering_cols):
            continue

        # ✅ 算法工程需求
        stats["engineering_requirements"] += 1

        # 标签匹配 — 优先找"自定义标签"，也兼容"自...标签"等异名
        for tag_col in ["自定义标签", "自...标签", "标签", "需求标签"]:
            if tag_col in row.index:
                tags_val = row.get(tag_col, "")
                break
        else:
            tags_val = ""
        if match_tags(tags_val, AICODING_KEYWORDS):
            stats["aicoding_count"] += 1
        if match_tags(tags_val, SDD_KEYWORDS):
            stats["sdd_count"] += 1
        if match_tags(tags_val, ENDTOEND_KEYWORDS):
            stats["endtoend_count"] += 1

        stats["details"].append({
            "prd_id": str(row.get("PRD ID", "")),
            "title": str(row.get("PRD标题", "")),
            "tags": str(tags_val),
        })

    # 计算占比
    stats["aicoding_ratio"] = (
        round(stats["aicoding_count"] / stats["engineering_requirements"] * 100, 2)
        if stats["engineering_requirements"] > 0 else 0
    )
    stats["sdd_ratio"] = (
        round(stats["sdd_count"] / stats["aicoding_count"] * 100, 2)
        if stats["aicoding_count"] > 0 else 0
    )

    return stats


def batch_process(files: List[str]) -> List[Dict[str, Any]]:
    """批量处理多个 xlsx 文件

    Args:
        files: xlsx 文件路径列表

    Returns:
        每个文件的统计结果列表
    """
    results = []
    for fp in files:
        try:
            df = parse_project_xlsx(fp)
            stats = calculate_stats(df)
            stats["source_file"] = Path(fp).name
            results.append(stats)
        except Exception as e:
            logger.error(f"处理 {fp} 失败: {e}")
            results.append({
                "source_file": Path(fp).name,
                "error": str(e),
            })
    return results


def build_project_stats_row(
    project_name: str,
    tl: str,
    total: int,
    engineering: int,
    aicoding: int,
    sdd: int,
    e2e: int,
) -> Dict[str, Any]:
    """构建项目统计数据行（供前端表格使用）

    占比计算规则（与飞书 wiki 公式一致）：
    - AICoding占比 = IF(工程=0, 0, AIcoding/工程)
    - SDD占比 = IF(AIcoding=0, 0, SDD/AIcoding)
    """
    aicoding_ratio = round(aicoding / engineering * 100, 2) if engineering > 0 else 0
    sdd_ratio = round(sdd / aicoding * 100, 2) if aicoding > 0 else 0

    return {
        "project_name": project_name,
        "tl": tl,
        "total": total,
        "engineering": engineering,
        "aicoding": aicoding,
        "aicoding_ratio": aicoding_ratio,
        "sdd": sdd,
        "sdd_ratio": sdd_ratio,
        "e2e": e2e,
    }