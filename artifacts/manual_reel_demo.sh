#!/usr/bin/env bash
# Manual reel creation end-to-end demo against the Content Laboratory API.
# Creates an org + page + reel family + reel, triggers the process_reel
# orchestrator flow (with Runway in mock mode), polls status, and downloads
# the final reel package artifacts (MP4 + cover + metadata) for the page.
set -euo pipefail

API="${API_BASE:-http://127.0.0.1:8000}"
ACTOR_ID="manual-demo-operator"
OUT_DIR="${OUT_DIR:-/workspace/artifacts}"
PAGE_DIR=""

hdr() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
sub() { printf "\033[0;37m    %s\033[0m\n" "$*"; }
val() { printf "\033[1;33m    %s\033[0m\n" "$*"; }

pp() { python3 -c 'import json,sys;print(json.dumps(json.load(sys.stdin), indent=2)[:1800])'; }

hdr "Step 1. Health check against Content Lab API at $API"
curl -sS "$API/health" | pp

hdr "Step 2. Provision a smoke-test org (direct SQL, since /orgs lacks a create route)"
ORG_ID=$(python3 -c 'import uuid;print(uuid.uuid4())')
SLUG="manual-demo-$(date -u +%Y%m%d%H%M%S)"
docker compose -f /workspace/infra/docker-compose.yml exec -T postgres \
  psql -U contentlab -d contentlab -v ON_ERROR_STOP=1 -At \
  -c "insert into orgs (id, name, slug) values ('$ORG_ID', 'Manual Demo Org', '$SLUG') returning id;"
val "ORG_ID = $ORG_ID"

hdr "Step 3. Create an owned page via POST /orgs/{org_id}/pages"
PAGE_JSON=$(curl -sS -X POST "$API/orgs/$ORG_ID/pages" \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: $ACTOR_ID" \
  -d '{
        "platform": "instagram",
        "display_name": "Manual Demo Page",
        "external_page_id": "manual-demo-'"$(date +%s)"'",
        "handle": "@manual_demo",
        "ownership": "owned",
        "metadata": {
          "persona": {"label": "Calm educator", "audience": "Busy founders", "content_pillars": ["operations"]},
          "constraints": {"allow_direct_cta": true, "max_hashtags": 4},
          "timezone": "UTC",
          "locale": "en"
        }
      }')
echo "$PAGE_JSON" | pp
PAGE_ID=$(echo "$PAGE_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
val "PAGE_ID = $PAGE_ID"

hdr "Step 4. Attach a page-scoped policy (100% explore, budgets)"
curl -sS -X PATCH "$API/orgs/$ORG_ID/policy/page/$PAGE_ID" \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: $ACTOR_ID" \
  -d '{"mode_ratios":{"exploit":0.0,"explore":1.0,"mutation":0.0,"chaos":0.0},
       "budget":{"per_run_usd_limit":20.0,"daily_usd_limit":50.0,"monthly_usd_limit":500.0}}' | pp

hdr "Step 5. Create a reel family on the page"
FAMILY_JSON=$(curl -sS -X POST "$API/orgs/$ORG_ID/pages/$PAGE_ID/reel-families" \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: $ACTOR_ID" \
  -d '{"name":"Manual Demo Family","mode":"explore","metadata":{"source":"manual-demo"}}')
echo "$FAMILY_JSON" | pp
FAMILY_ID=$(echo "$FAMILY_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
val "FAMILY_ID = $FAMILY_ID"

hdr "Step 6. Create a single generated reel (draft) in that family"
REEL_JSON=$(curl -sS -X POST "$API/orgs/$ORG_ID/pages/$PAGE_ID/reel-families/$FAMILY_ID/reels" \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: $ACTOR_ID" \
  -d '{"origin":"generated","status":"draft","variant_label":"v1","metadata":{"source":"manual-demo"}}')
echo "$REEL_JSON" | pp
REEL_ID=$(echo "$REEL_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
val "REEL_ID = $REEL_ID"

hdr "Step 7. Trigger the process_reel flow for that reel"
RUN_JSON=$(curl -sS -X POST "$API/orgs/$ORG_ID/pages/$PAGE_ID/reels/$REEL_ID/trigger" \
  -H "Content-Type: application/json" \
  -H "X-Actor-Id: $ACTOR_ID" \
  -d '{"input_params":{"priority":"high"},"metadata":{"source":"manual-demo"}}')
echo "$RUN_JSON" | pp
RUN_ID=$(echo "$RUN_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
val "RUN_ID = $RUN_ID"

hdr "Step 8. Execute the Prefect process_reel flow (RUNWAY_API_MODE=mock)"
(
  cd /workspace/apps/orchestrator
  RUNWAY_API_MODE=mock ~/.local/bin/poetry run python -m content_lab_orchestrator.cli run \
    --flow process_reel --reel-id "$REEL_ID" --run-id "$RUN_ID" 2>&1 | tail -25
)

hdr "Step 9. Fetch final run / reel / package status"
echo "--- Run detail ---"
curl -sS "$API/orgs/$ORG_ID/runs/$RUN_ID" -H "X-Actor-Id: $ACTOR_ID" | pp
echo "--- Reel detail ---"
curl -sS "$API/orgs/$ORG_ID/pages/$PAGE_ID/reels/$REEL_ID" -H "X-Actor-Id: $ACTOR_ID" | pp
echo "--- Package (with presigned URLs) ---"
PKG_JSON=$(curl -sS "$API/orgs/$ORG_ID/packages/$RUN_ID" -H "X-Actor-Id: $ACTOR_ID")
echo "$PKG_JSON" | pp

hdr "Step 10. Download the reel package for the page (MP4 + cover + metadata)"
PAGE_DIR="$OUT_DIR/page/$PAGE_ID/reel/$REEL_ID"
mkdir -p "$PAGE_DIR"
echo "$PKG_JSON" > "$PAGE_DIR/package.json"

python3 - "$PKG_JSON" "$PAGE_DIR" <<'PY'
import json, sys, urllib.request, os
pkg = json.loads(sys.argv[1])
out_dir = sys.argv[2]
for art in pkg.get("artifacts", []):
    name = art.get("name")
    dl = art.get("download", {}) or {}
    url = dl.get("url") or art.get("uri")
    ext = {
        "final_video": "mp4",
        "cover": "png",
        "caption_variants": "txt",
        "posting_plan": "json",
    }.get(name, "bin")
    if not url:
        print(f"  (!) no download url for {name}")
        continue
    dest = os.path.join(out_dir, f"{name}.{ext}")
    urllib.request.urlretrieve(url, dest)
    size = os.path.getsize(dest)
    print(f"  downloaded {name:22s} -> {dest} ({size} bytes)")
PY

ls -la "$PAGE_DIR"
file "$PAGE_DIR"/final_video.mp4 2>/dev/null || true

hdr "Summary"
echo "org_id   : $ORG_ID"
echo "page_id  : $PAGE_ID"
echo "family_id: $FAMILY_ID"
echo "reel_id  : $REEL_ID"
echo "run_id   : $RUN_ID"
echo "artifacts: $PAGE_DIR"

cat > "$OUT_DIR/last_run_ids.json" <<EOF
{
  "org_id": "$ORG_ID",
  "page_id": "$PAGE_ID",
  "family_id": "$FAMILY_ID",
  "reel_id": "$REEL_ID",
  "run_id": "$RUN_ID",
  "artifacts_dir": "$PAGE_DIR"
}
EOF
