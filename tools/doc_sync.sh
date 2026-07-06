#!/bin/bash
# doc-sync — 文档同步检查脚本
# 在开始新功能或声称任务完成前运行一次
# 用法: bash tools/doc_sync.sh [check|status]

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

DOCS=(
  "progress.md:进度日志"
  "MEMORY.md:长期记忆"
  "task_plan.md:任务追踪"
  "IMPLEMENTATION_PLAN.md:实施方案"
  "findings.md:技术发现"
  "BLOG_RECORD.md:博客素材"
)

# 关键代码目录
CODE_DIRS=(
  "backend/services"
  "backend/routers"
  "frontend/src/pages"
  "frontend/src/components"
)

get_latest_code_time() {
  local latest=0
  for dir in "${CODE_DIRS[@]}"; do
    if [ -d "$dir" ]; then
      t=$(find "$dir" -name "*.py" -o -name "*.tsx" -o -name "*.ts" 2>/dev/null | xargs -I{} stat -f "%m" {} 2>/dev/null | sort -rn | head -1)
      if [ -n "$t" ] && [ "$t" -gt "$latest" ]; then
        latest=$t
      fi
    fi
  done
  echo "$latest"
}

get_doc_time() {
  if [ -f "$1" ]; then
    stat -f "%m" "$1" 2>/dev/null || echo "0"
  else
    echo "0"
  fi
}

fmt_time() {
  if [ "$1" = "0" ]; then
    echo "不存在"
  else
    date -r "$1" "+%m-%d %H:%M" 2>/dev/null || echo "未知"
  fi
}

fmt_ago() {
  if [ "$1" = "0" ]; then
    echo "-"
    return
  fi
  local now
  now=$(date +%s)
  local diff=$((now - $1))
  if [ $diff -lt 60 ]; then
    echo "${diff}秒前"
  elif [ $diff -lt 3600 ]; then
    echo "$((diff / 60))分钟前"
  elif [ $diff -lt 86400 ]; then
    echo "$((diff / 3600))小时前"
  else
    echo "$((diff / 86400))天前"
  fi
}

echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo -e "${CYAN}  文档同步检查 — doc-sync            ${NC}"
echo -e "${CYAN}═══════════════════════════════════════${NC}"
echo ""

latest_code=$(get_latest_code_time)
echo -e "最新代码修改: $(fmt_time "$latest_code") ($(fmt_ago "$latest_code"))"
echo ""

echo -e "${YELLOW}文档状态 (代码修改在前 / 文档修改在后 → 已同步):${NC}"
echo ""

STALE=0
for entry in "${DOCS[@]}"; do
  file="${entry%%:*}"
  label="${entry##*:}"
  dt=$(get_doc_time "$file")
  code_time=$latest_code
  if [ "$dt" -ge "$code_time" ]; then
    echo -e "  ${GREEN}✅${NC} $label — $(fmt_time "$dt")"
  else
    echo -e "  ${RED}❌${NC} $label — $(fmt_time "$dt") (代码更新于 $(fmt_ago "$latest_code"))"
    STALE=$((STALE + 1))
  fi
done

echo ""
if [ "$STALE" -gt 0 ]; then
  echo -e "${RED}⚠️  有 $STALE 个文档滞后于代码${NC}"
  echo ""
  echo -e "${YELLOW}建议更新内容:${NC}"
  echo ""
  for entry in "${DOCS[@]}"; do
    file="${entry%%:*}"
    label="${entry##*:}"
    dt=$(get_doc_time "$file")
    if [ "$dt" -lt "$latest_code" ]; then
      case "$label" in
        "进度日志")
          echo "  • $label ($file) — 追加本次操作的进度记录"
          ;;
        "长期记忆")
          echo "  • $label ($file) — 更新 Phase 状态/修复记录/工具设置"
          ;;
        "任务追踪")
          echo "  • $label ($file) — 更新 Task 状态（done/in_progress/not_started）"
          ;;
        "实施方案")
          echo "  • $label ($file) — 对齐实际实现与方案描述"
          ;;
        "技术发现")
          echo "  • $label ($file) — 补充新的技术教训"
          ;;
        "博客素材")
          echo "  • $label ($file) — 追加故事性事件记录"
          ;;
      esac
    fi
  done
  echo ""
  echo -e "${YELLOW}执行: 逐个阅读并更新上述文件后才可进入下一阶段${NC}"
  exit 1
else
  echo -e "${GREEN}✅ 所有文档已同步至最新代码版本${NC}"
  exit 0
fi