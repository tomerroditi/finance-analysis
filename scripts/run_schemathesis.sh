#!/usr/bin/env bash
#
# Run Schemathesis against the locally-running FastAPI app to fuzz the
# OpenAPI 3.1 schema served at /openapi.json. Designed to be invoked by CI
# (see .github/workflows/ci.yml) after the backend has been started in the
# background.
#
# Schema exclusions:
#   - /api/testing/*               — flips demo mode globally; would break
#                                    other test runs sharing this process.
#   - /api/scraping/*              — kicks off real scraping jobs (5-minute
#                                    timeout, daily rate limits).
#   - /api/credentials/*           — writes to OS keyring; mutating or
#                                    reading these in fuzzing is unsafe.
#   - /api/backups/*               — creates / restores the user DB; not
#                                    something a fuzz run should touch.
#   - /api/updates/*               — makes a real outbound HTTP call to the
#                                    GitHub releases API (5s timeout, 60
#                                    req/hr unauthenticated rate limit). It is
#                                    non-deterministic, slow on a cache miss
#                                    (which trips the hypothesis deadline),
#                                    and fuzzing it burns GitHub's rate limit.
#
# Method exclusions:
#   - DELETE / PUT / POST mutate state. We restrict to GET so a single CI
#     run can hammer the API without leaving the demo DB in a bad shape.
#     Mutation fuzzing belongs in a dedicated job that owns its DB lifecycle.

set -euo pipefail

BASE_URL="${SCHEMATHESIS_BASE_URL:-http://localhost:8000}"
SCHEMA_URL="${BASE_URL}/openapi.json"
MAX_EXAMPLES="${SCHEMATHESIS_MAX_EXAMPLES:-25}"

echo "Fuzzing ${SCHEMA_URL} (max examples per endpoint: ${MAX_EXAMPLES})"

poetry run schemathesis run "${SCHEMA_URL}" \
  --base-url "${BASE_URL}" \
  --experimental=openapi-3.1 \
  --include-method=GET \
  --exclude-path-regex='^/api/(testing|scraping|credentials|backups|updates)' \
  --hypothesis-max-examples="${MAX_EXAMPLES}" \
  --hypothesis-deadline=2000 \
  --hypothesis-suppress-health-check=too_slow,filter_too_much,data_too_large \
  --workers=2 \
  --request-timeout=5000 \
  --checks=not_a_server_error
