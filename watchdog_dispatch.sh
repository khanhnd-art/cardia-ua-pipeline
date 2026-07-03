#!/bin/bash
# Cardia — watchdog chống GitHub bỏ mốc cron: nếu run cuối của pipeline.yml cũ hơn 75 phút
# thì tự kích workflow_dispatch qua gh CLI (GitHub không bao giờ drop dispatch).
# Chạy bởi launchd (com.cardia.watchdog) phút 37 mỗi giờ, khi máy Mac đang thức.
# Đây là LƯỚI DỰ PHÒNG — lịch chính vẫn là cron GitHub Actions (phút 7). Máy tắt → chỉ còn cron chính.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
REPO="khanhnd-art/cardia-ua-pipeline"
STALE_SEC=4500   # 75 phút

command -v gh >/dev/null 2>&1 || { echo "$(date '+%F %T') ⏭ chưa cài gh"; exit 0; }
LAST=$(gh run list -R "$REPO" --workflow pipeline.yml --limit 1 --json createdAt --jq '.[0].createdAt' 2>/dev/null)
[ -z "$LAST" ] && { echo "$(date '+%F %T') ⏭ không đọc được run list (mạng/auth?)"; exit 0; }
LAST_EPOCH=$(date -j -u -f "%Y-%m-%dT%H:%M:%SZ" "$LAST" +%s 2>/dev/null) || { echo "$(date '+%F %T') ⏭ parse lỗi: $LAST"; exit 0; }
AGE=$(( $(date +%s) - LAST_EPOCH ))

if [ "$AGE" -gt "$STALE_SEC" ]; then
  echo "$(date '+%F %T') 🚨 run cuối cách $((AGE/60))p (>75p) → kích workflow_dispatch"
  gh workflow run pipeline.yml -R "$REPO" && echo "$(date '+%F %T') ✅ đã dispatch"
else
  echo "$(date '+%F %T') OK — run cuối cách $((AGE/60))p"
fi
