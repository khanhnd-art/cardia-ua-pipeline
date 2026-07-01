#!/bin/bash
# Cardia — chạy toàn bộ pipeline UA 1 phát: pull → analyze → dashboard → weekly report.
# Dùng cho launchd/cron (chạy tự động) hoặc gọi tay. Ghi log vào ./logs/<ngày>.log.
# Cron PATH tối giản → dùng đường dẫn tuyệt đối.

set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
PY=/usr/bin/python3                       # python3 hệ thống macOS (có sẵn)
TODAY="$(date +%Y-%m-%d)"
mkdir -p "$HERE/logs"
LOG="$HERE/logs/$TODAY.log"

cd "$HERE" || exit 1
{
  echo "===== Cardia pipeline @ $(date) ====="
  echo "--- pull_data ---";     "$PY" pull_data.py
  echo "--- dashboard ---";     "$PY" dashboard.py
  echo "--- publish ---";        bash publish_cloudflare.sh
} >> "$LOG" 2>&1

# analyze chạy 1 lần, lưu cả vào log lẫn file đọc nhanh _latest_analysis.txt
"$PY" analyze.py 2>&1 | tee "$HERE/_latest_analysis.txt" >> "$LOG"
echo "===== xong @ $(date) =====" >> "$LOG"
echo "✅ Pipeline xong → log: $LOG · phân tích: _latest_analysis.txt"
