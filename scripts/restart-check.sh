#!/usr/bin/env bash
# 重启恢复检查钩子（契约见通用手册第十节）。
# verify.sh 负责：起服务 → 写标记 → kill -9 → 再起 → 读回比对。
# 本脚本只提供四个动作，不调真实模型（写操作走「创建报告」，不需要模型）。
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"          # 产品文件夹
BACKEND="$ROOT/backend"
DIR="${RESTART_CHECK_DIR:-$(mktemp -d)}"
PORT="${RESTART_CHECK_PORT:-8099}"
mkdir -p "$DIR/uploads"
PIDFILE="$DIR/server.pid"

start_server() {
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "端口 $PORT 被占用，请先释放（不动别的进程）" >&2
    return 1
  fi
  cd "$BACKEND" || return 1
  DATABASE_URL="sqlite:///$DIR/app.db" \
  UPLOAD_DIR="$DIR/uploads" \
  DEEPSEEK_API_KEY="" \
  MOCK_LLM=1 \
  nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
        > "$DIR/server.log" 2>&1 &
  PID=$!
  echo "$PID" > "$PIDFILE"
  for _ in $(seq 1 100); do
    if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
      echo "$PID"
      return 0
    fi
    sleep 0.2
  done
  echo "服务在 20 秒内没起来，见 $DIR/server.log" >&2
  return 1
}

case "${1:-}" in
  start)
    start_server
    ;;
  write)
    MARK="${2:-}"
    [ -z "$MARK" ] && { echo "缺少标记" >&2; exit 1; }
    RESP="$(curl -fsS -X POST "http://127.0.0.1:$PORT/api/reports" \
      -H 'Content-Type: application/json' \
      -d "{\"title\":\"$MARK\"}")" || { echo "写入失败" >&2; exit 1; }
    printf '%s' "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
    ;;
  read)
    ID="${2:-}"
    [ -z "$ID" ] && { echo "缺少记录 ID" >&2; exit 1; }
    curl -fsS "http://127.0.0.1:$PORT/api/reports/$ID" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["title"])'
    ;;
  stop)
    if [ -f "$PIDFILE" ]; then
      kill "$(cat "$PIDFILE")" 2>/dev/null || true
      rm -f "$PIDFILE"
    fi
    PIDS="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)"
    [ -n "$PIDS" ] && kill $PIDS 2>/dev/null || true
    [ -n "${KEEP:-}" ] || rm -rf "$DIR" 2>/dev/null || true
    echo "stopped"
    ;;
  *)
    echo "用法：restart-check.sh start|write <标记>|read <ID>|stop" >&2
    exit 2
    ;;
esac
