#!/bin/bash
# Đẩy toàn bộ biến trong .env local lên GitHub Secrets của repo (khỏi copy-paste tay).
# Yêu cầu: đã cài GitHub CLI (`brew install gh`) và `gh auth login`.
# Dùng:  bash push-secrets.sh <owner/repo>
#   vd:  bash push-secrets.sh khanhnd/cardia-ua-pipeline
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; cd "$HERE"

REPO="${1:-}"
[ -z "$REPO" ] && { echo "❌ Thiếu tham số. Dùng: bash push-secrets.sh <owner/repo>"; exit 1; }
[ -f .env ] || { echo "❌ Không thấy .env trong $HERE"; exit 1; }
command -v gh >/dev/null || { echo "❌ Chưa cài gh (brew install gh) hoặc chưa gh auth login"; exit 1; }

# Chỉ đẩy đúng các key pipeline cần (bỏ comment, dòng trống).
KEYS="META_ACCESS_TOKEN META_AD_ACCOUNT_ID ADJUST_API_TOKEN ADJUST_REPORT_QUERY ADJUST_CREATIVE_QUERY ADJUST_SAYA_QUERY SINCE CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID CF_PAGES_PROJECT"

for k in $KEYS; do
  # Lấy value từ .env: dòng ^KEY= , bỏ nháy bao ngoài.
  v="$(grep -E "^${k}=" .env | head -1 | sed -E "s/^${k}=//; s/^[\"']//; s/[\"']$//")"
  if [ -z "$v" ]; then
    echo "⚠️  Bỏ qua $k (rỗng trong .env)"
    continue
  fi
  printf '%s' "$v" | gh secret set "$k" --repo "$REPO"
  echo "✅ $k"
done
echo "🎉 Xong. Kiểm tra: Settings → Secrets and variables → Actions ở repo $REPO"
