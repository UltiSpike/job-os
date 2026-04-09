#!/usr/bin/env bash
# 检查影响 Claude Code 速度的客观因素
set -u

GREEN='\033[32m'; YELLOW='\033[33m'; RED='\033[31m'; DIM='\033[2m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
bad()  { echo -e "${RED}✗${NC} $1"; }
hdr()  { echo; echo -e "${DIM}── $1 ──${NC}"; }

hdr "1. 网络延迟 (api.anthropic.com)"
if command -v curl >/dev/null; then
  for i in 1 2 3; do
    t=$(curl -o /dev/null -s -w '%{time_connect} %{time_starttransfer} %{http_code}\n' \
      --max-time 10 https://api.anthropic.com/v1/messages 2>/dev/null || echo "fail")
    echo "  尝试$i: $t  (connect / ttfb / code)"
  done
  ttfb=$(curl -o /dev/null -s -w '%{time_starttransfer}' --max-time 10 https://api.anthropic.com/ 2>/dev/null || echo 0)
  awk -v t="$ttfb" 'BEGIN{
    if (t+0==0) print "  → 无法连接，检查代理/VPN";
    else if (t+0 < 0.5) print "  → 延迟良好";
    else if (t+0 < 1.5) print "  → 延迟一般";
    else print "  → 延迟较高，建议换节点/代理";
  }'
else
  bad "未安装 curl"
fi

hdr "2. 代理设置"
for v in HTTPS_PROXY https_proxy HTTP_PROXY http_proxy ALL_PROXY all_proxy; do
  val="${!v:-}"
  [ -n "$val" ] && echo "  $v=$val"
done
[ -z "${HTTPS_PROXY:-}${https_proxy:-}${ALL_PROXY:-}${all_proxy:-}" ] && warn "未检测到代理（国内直连通常较慢）"

hdr "3. DNS 解析"
if command -v dig >/dev/null; then
  dig +short +time=2 api.anthropic.com | head -3 | sed 's/^/  /'
elif command -v nslookup >/dev/null; then
  nslookup api.anthropic.com 2>/dev/null | grep -A2 'Name:' | sed 's/^/  /'
fi

hdr "4. 系统负载 / 资源"
uptime | sed 's/^/  /'
mem=$(vm_stat 2>/dev/null | awk '
  /Pages free/      {f=$3}
  /Pages active/    {a=$3}
  /Pages inactive/  {i=$3}
  /Pages wired/     {w=$4}
  END{
    gsub(/\./,"",f); gsub(/\./,"",a); gsub(/\./,"",i); gsub(/\./,"",w);
    total=(f+a+i+w)*4096/1024/1024/1024;
    used=(a+w)*4096/1024/1024/1024;
    printf "  内存: %.1f / %.1f GB used\n", used, total;
  }')
echo "$mem"
df -h / 2>/dev/null | awk 'NR==2{printf "  磁盘: %s used / %s total (%s)\n",$3,$2,$5}'

hdr "5. Claude Code 进程"
ps -axo pid,pcpu,pmem,comm | grep -i claude | grep -v grep | head -5 | sed 's/^/  /' || echo "  (未发现进程)"

hdr "6. 当前会话上下文体积"
proj_dir="$HOME/.claude/projects/-Users-<user>--Projects-my-project-job-os"
if [ -d "$proj_dir" ]; then
  du -sh "$proj_dir" 2>/dev/null | sed 's/^/  /'
  latest=$(ls -t "$proj_dir"/*.jsonl 2>/dev/null | head -1)
  if [ -n "$latest" ]; then
    sz=$(wc -c < "$latest" | tr -d ' ')
    lines=$(wc -l < "$latest" | tr -d ' ')
    echo "  最近会话: $(basename "$latest")"
    echo "  大小: $((sz/1024)) KB, $lines 条消息"
    if [ "$sz" -gt 2000000 ]; then
      warn "会话很大，建议 /clear 开新会话"
    fi
  fi
fi

hdr "7. 仓库体积 (影响 ToolSearch / 索引)"
du -sh . 2>/dev/null | sed 's/^/  /'
file_count=$(find . -type f -not -path './.git/*' 2>/dev/null | wc -l | tr -d ' ')
echo "  非 .git 文件数: $file_count"

hdr "建议"
cat <<EOF
  • 当前模型: Opus 4.6 (1M ctx) — 比 Sonnet/Haiku 慢，可 /model 切换
  • 试 /fast 开启快速输出
  • 上下文 > 2MB 时 /clear 开新会话
  • TTFB > 1.5s 时换代理节点
  • 看 https://status.anthropic.com 排除服务端问题
EOF
