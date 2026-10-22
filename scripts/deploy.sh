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

# Wrangler is a native Windows binary and does not understand MSYS paths
# ("/c/Users/..." becomes "C:\c\Users\..."). Convert to a native path.
to_native() {
  case "$1" in
    /[A-Za-z]/*) printf '%s:%s\n' "$(printf '%s' "$1" | cut -c2 | tr '[:lower:]' '[:upper:]')" "$(printf '%s' "$1" | cut -c3- | tr '/' '\\')" ;;
    *) printf '%s\n' "$1" ;;
  esac
}
SITE_NATIVE="$(to_native "$SITE_PATH")"

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
#    The existence check must look at the JSON `success` field, not grep for
#    '"success":true' in the raw body (which fails when the body is
#    pretty-printed across lines).
EXISTS=$(curl -s "${AUTH[@]}" "$CF/accounts/$ACC/pages/projects/$PROJECT" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('yes' if d.get('success') else 'no')" 2>/dev/null || echo no)
if [ "$EXISTS" = "yes" ]; then
  echo "project: $PROJECT (exists)"
else
  # The *.pages.dev name must not already belong to another Cloudflare
  # account, or the CNAME triggers "error 1014: CNAME Cross-User Banned"
  # and the domain 403s. Verified 2026-10-22 with "solar" (taken by
  # "Derviş Solar") and "solarcalc" (also taken).
  TAKEN=$(curl -s -o /dev/null -w "%{http_code}" -m 20 "https://$PROJECT.pages.dev/" || echo 000)
  if [ "$TAKEN" = "200" ]; then
    echo "ERROR: $PROJECT.pages.dev is already taken by another account." >&2
    echo "       Pick a different project name. Cloudflare would answer 1014/403." >&2
    exit 4
  fi
  echo "project: $PROJECT (creating; $PROJECT.pages.dev is free)"
  wrangler pages project create "$PROJECT" --production-branch=main
fi

# Read back the real subdomain: Cloudflare may append a numeric suffix
# (e.g. "solar" -> "solar-6f3.pages.dev").
SUBDOMAIN=$(curl -s "${AUTH[@]}" "$CF/accounts/$ACC/pages/projects/$PROJECT" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('result',{}).get('subdomain',''))" 2>/dev/null || echo "")
if [ -z "$SUBDOMAIN" ]; then
  echo "ERROR: could not read the project subdomain" >&2
  exit 3
fi
echo "subdomain: $SUBDOMAIN"

# 2. Deploy.
echo "deploying $SITE_NATIVE ..."
wrangler pages deploy "$SITE_NATIVE" --project-name="$PROJECT" --branch=main --commit-dirty=true

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

  # The CNAME target must be the CANONICAL project name (<project>.pages.dev),
  # not the subdomain Pages actually assigned (which may carry a numeric
  # suffix like "solar-6f3.pages.dev"). Verified 2026-10-22: pointing at the
  # suffixed subdomain returns HTTP 522; pointing at the canonical name works.
  CNAME_TARGET="$PROJECT.pages.dev"

  # Ensure a CNAME to the canonical project name.
  EXIST=$(curl -s "${AUTH[@]}" "$CF/zones/$ZONE_ID/dns_records?name=$HOSTNAME" \
    | python3 -c "import sys,json;r=json.load(sys.stdin).get('result',[]);print(r[0]['id'] if r else '')")
  if [ -n "$EXIST" ]; then
    echo "  dns record exists"
    # Keep the target pointing at the right project even if it changed.
    curl -s -X PUT "${AUTH[@]}" "$CF/zones/$ZONE_ID/dns_records/$EXIST" \
      -d "{\"type\":\"CNAME\",\"name\":\"$HOSTNAME\",\"content\":\"$CNAME_TARGET\",\"proxied\":true,\"ttl\":1}" \
      | python3 -c "import sys,json;d=json.load(sys.stdin);print('  dns -> '+str(d.get('result',{}).get('content','')) if d.get('success') else '  dns update: '+str(d.get('errors')))"
  else
    curl -s -X POST "${AUTH[@]}" "$CF/zones/$ZONE_ID/dns_records" \
      -d "{\"type\":\"CNAME\",\"name\":\"$HOSTNAME\",\"content\":\"$CNAME_TARGET\",\"proxied\":true,\"ttl\":1}" \
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
echo "live: https://$SUBDOMAIN/"
[ -n "$HOSTNAME" ] && echo "live: https://$HOSTNAME/"
exit 0
