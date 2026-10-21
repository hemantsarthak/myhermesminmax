#!/usr/bin/env bash
# Deploy a static site to Cloudflare Pages + attach a custom domain on tekify.xyz.
#
# Usage:
#   scripts/deploy.sh <site-dir> <project-name> [hostname]
#   scripts/deploy.sh sites/pool-chem poolchem pool.tekify.xyz
#
# Idempotent. Safe to re-run. Prints the live URL at the end.
set -euo pipefail

SITE_DIR="${1:?usage: deploy.sh <site-dir> <project-name> [hostname]}"
PROJECT="${2:?usage: deploy.sh <site-dir> <project-name> [hostname]}"
HOSTNAME="${3:-}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE missing. Run: python3 scripts/parse_creds.py" >&2
  exit 2
fi
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
  echo "ERROR: CLOUDFLARE_API_TOKEN not set" >&2
  exit 2
fi

SITE_PATH="$(cd "$SITE_DIR" 2>/dev/null && pwd || echo "")"
if [ -z "$SITE_PATH" ]; then
  echo "ERROR: site dir not found: $SITE_DIR" >&2
  exit 2
fi

CF="https://api.cloudflare.com/client/v4"
AUTH=(-H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json")
ACC="$CLOUDFLARE_ACCOUNT_ID"

# Resolve the zone id for the primary domain.
ZONE_NAME="${PRIMARY_DOMAIN:-tekify.xyz}"
ZONE_ID=$(curl -s "${AUTH[@]}" "$CF/zones?name=$ZONE_NAME" \
  | python3 -c "import sys,json;r=json.load(sys.stdin).get('result',[]);print(r[0]['id'] if r else '')")
if [ -z "$ZONE_ID" ]; then
  echo "ERROR: zone $ZONE_NAME not found in this account" >&2
  exit 3
fi
echo "zone: $ZONE_NAME ($ZONE_ID)"

# 1. Ensure the Pages project exists.
if curl -s "${AUTH[@]}" "$CF/accounts/$ACC/pages/projects/$PROJECT" | grep -q '"success":true'; then
  echo "project: $PROJECT (exists)"
else
  echo "project: $PROJECT (creating)"
  wrangler pages project create "$PROJECT" --production-branch=main
fi

# 2. Deploy.
echo "deploying $SITE_PATH ..."
wrangler pages deploy "$SITE_PATH" --project-name="$PROJECT" --branch=main --commit-dirty=true

# 3. Attach the custom domain (optional).
if [ -n "$HOSTNAME" ]; then
  echo "attaching domain $HOSTNAME"
  # Add the domain to the project (idempotent; 8000007 = already attached).
  curl -s -X POST "${AUTH[@]}" "$CF/accounts/$ACC/pages/projects/$PROJECT/domains" \
    -d "{\"name\":\"$HOSTNAME\"}" | python3 -c "
import sys,json
d=json.load(sys.stdin)
if d.get('success'):
    print('  domain added:', d['result'].get('name'))
else:
    errs=d.get('errors',[])
    msg='; '.join(str(e.get('message',e)) for e in errs)
    print('  domain add:', 'already attached' if 'already' in msg.lower() else msg)
"

  # Ensure a CNAME to the project subdomain.
  EXIST=$(curl -s "${AUTH[@]}" "$CF/zones/$ZONE_ID/dns_records?name=$HOSTNAME" \
    | python3 -c "import sys,json;r=json.load(sys.stdin).get('result',[]);print(r[0]['id'] if r else '')")
  if [ -n "$EXIST" ]; then
    echo "  dns record exists"
  else
    curl -s -X POST "${AUTH[@]}" "$CF/zones/$ZONE_ID/dns_records" \
      -d "{\"type\":\"CNAME\",\"name\":\"$HOSTNAME\",\"content\":\"$PROJECT.pages.dev\",\"proxied\":true,\"ttl\":1}" \
      | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('  dns record:', d['result']['name'] if d.get('success') else d.get('errors'))
"
  fi

  sleep 5
  echo -n "verify https://$HOSTNAME -> "
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 25 "https://$HOSTNAME/" || echo 000)
  echo "HTTP $CODE"
fi

echo
echo "live: https://$PROJECT.pages.dev/"
[ -n "$HOSTNAME" ] && echo "live: https://$HOSTNAME/"
exit 0
