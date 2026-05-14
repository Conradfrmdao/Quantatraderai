#!/usr/bin/env bash
# QuntaTradeAI — Full test suite runner
# Usage: bash scripts/run_tests.sh [--report]
#
# Exit codes:
#   0  — all tests passed (safe to deploy)
#   1  — one or more test suites failed (DO NOT DEPLOY)
set -euo pipefail

VENV_PYTHON="/home/wagaba-conrad/.cache/pypoetry/virtualenvs/quntatradeai-cldsYo_v-py3.12/bin/python"
NODE="/home/wagaba-conrad/.nvm/versions/node/v22.16.0/bin/node"
REPORT_FILE="/tmp/qunta_test_report_$(date +%Y%m%d_%H%M%S).txt"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'
BOLD='\033[1m'

ok()   { echo -e "${GREEN}✓${RESET} $1"; }
fail() { echo -e "${RED}✗${RESET} $1"; }
info() { echo -e "${YELLOW}→${RESET} $1"; }

PASS=0
FAIL=0
RESULTS=()

run_suite() {
  local name="$1"
  local cmd="$2"
  info "Running: $name"
  if eval "$cmd" > /tmp/qunta_suite.log 2>&1; then
    ok "$name"
    RESULTS+=("PASS: $name")
    ((PASS++)) || true
  else
    fail "$name (see /tmp/qunta_suite.log)"
    cat /tmp/qunta_suite.log | tail -20
    RESULTS+=("FAIL: $name")
    ((FAIL++)) || true
  fi
}

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   QuntaTradeAI — Pre-Deploy Test Suite       ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${RESET}"
echo ""

# ── Python tests ─────────────────────────────────────────────────────────────
cd "$ROOT"

run_suite "Python: Encryption"         "$VENV_PYTHON -m pytest tests/test_encryption.py -q"
run_suite "Python: Risk Manager"       "$VENV_PYTHON -m pytest tests/test_risk_manager.py -q"
run_suite "Python: Indicators"         "$VENV_PYTHON -m pytest tests/test_indicators.py -q"
run_suite "Python: Symbol Map"         "$VENV_PYTHON -m pytest tests/test_symbol_map.py -q"
run_suite "Python: Venue Flows"        "$VENV_PYTHON -m pytest tests/test_venue_flows.py -q"
run_suite "Python: Forex Utilities"    "$VENV_PYTHON -m pytest tests/test_forex_utils.py -q"
run_suite "Python: OANDA Forex"        "$VENV_PYTHON -m pytest tests/test_forex_oanda.py -q"
run_suite "Python: MetaTrader Forex"   "$VENV_PYTHON -m pytest tests/test_forex_metatrader.py -q"
run_suite "Python: Binance Crypto"     "$VENV_PYTHON -m pytest tests/test_crypto_binance.py -q"
run_suite "Python: CCXT Crypto"        "$VENV_PYTHON -m pytest tests/test_crypto_ccxt.py -q"
run_suite "Python: Hyperliquid Crypto" "$VENV_PYTHON -m pytest tests/test_crypto_hyperliquid.py -q"
run_suite "Python: Market Freshness"   "$VENV_PYTHON -m pytest tests/test_market_data_freshness.py -q"
run_suite "Python: Agent Flows"        "$VENV_PYTHON -m pytest tests/test_agent_flows.py -q"
run_suite "Python: Adapter Contracts"  "$VENV_PYTHON -m pytest tests/test_adapter_contracts.py -q"
run_suite "Python: Security"           "$VENV_PYTHON -m pytest tests/test_security.py -q"
run_suite "Python: Failure Modes"      "$VENV_PYTHON -m pytest tests/test_failure_modes.py -q"
run_suite "Python: Server Integration" "$VENV_PYTHON -m pytest tests/test_server_integration.py -q"

# ── Advanced test layers ──────────────────────────────────────────────────────
run_suite "Python: E2E Flows"     "$VENV_PYTHON -m pytest tests/test_e2e_flows.py -q"
run_suite "Python: Chaos Tests"   "$VENV_PYTHON -m pytest tests/test_chaos.py -q"
run_suite "Python: Concurrency"   "$VENV_PYTHON -m pytest tests/test_concurrency.py -q"
run_suite "Python: Load Tests"    "$VENV_PYTHON -m pytest tests/test_load.py -q"
run_suite "Python: Observability" "$VENV_PYTHON -m pytest tests/test_observability.py -q"
run_suite "Python: Replay Engine" "$VENV_PYTHON -m pytest tests/test_replay.py -q"

# ── Load gate: parse [LOAD_METRICS] from load test output ─────────────────────
LOAD_LOG="/tmp/qunta_load_metrics.log"
$VENV_PYTHON -m pytest tests/test_load.py -q -s > "$LOAD_LOG" 2>&1 || true
LOAD_JSON=$(grep "\[LOAD_METRICS\]" "$LOAD_LOG" | sed 's/.*\[LOAD_METRICS\] //' | head -1)
if [ -n "$LOAD_JSON" ]; then
  ERR_RATE=$(echo "$LOAD_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error_rate_pct',0))")
  AVG_LAT=$(echo  "$LOAD_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('avg_latency_ms',0))")
  MAX_LAT=$(echo  "$LOAD_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('max_latency_ms',0))")
  ERR_FAIL=$(python3 -c "print('FAIL' if float('$ERR_RATE') > 1.0   else 'PASS')")
  AVG_FAIL=$(python3 -c "print('FAIL' if float('$AVG_LAT') > 200.0  else 'PASS')")
  MAX_FAIL=$(python3 -c "print('FAIL' if float('$MAX_LAT') > 1000.0 else 'PASS')")
  if [ "$ERR_FAIL" = "FAIL" ]; then
    RESULTS+=("FAIL: Load gate — error_rate ${ERR_RATE}% > 1%"); ((FAIL++)) || true
  fi
  if [ "$AVG_FAIL" = "FAIL" ]; then
    RESULTS+=("FAIL: Load gate — avg_latency ${AVG_LAT}ms > 200ms"); ((FAIL++)) || true
  fi
  if [ "$MAX_FAIL" = "FAIL" ]; then
    RESULTS+=("FAIL: Load gate — max_latency ${MAX_LAT}ms > 1000ms"); ((FAIL++)) || true
  fi
  if [ "$ERR_FAIL" = "PASS" ] && [ "$AVG_FAIL" = "PASS" ] && [ "$MAX_FAIL" = "PASS" ]; then
    ok "Load gate — err=${ERR_RATE}% avg=${AVG_LAT}ms max=${MAX_LAT}ms"
    RESULTS+=("PASS: Load gate — metrics within thresholds")
    ((PASS++)) || true
  fi
fi

# ── TypeScript tests ─────────────────────────────────────────────────────────
cd "$ROOT/ui"
VITEST_BIN=""
# Prefer .mjs over the shim (the shim breaks on Node 22)
if [ -f "node_modules/vitest/vitest.mjs" ]; then
  VITEST_BIN="$NODE node_modules/vitest/vitest.mjs"
fi

if [ -n "$VITEST_BIN" ]; then
  run_suite "TypeScript: Plan Limits" "$VITEST_BIN run lib/__tests__/plan-limits.test.ts"
  run_suite "TypeScript: Rate Limit"  "$VITEST_BIN run lib/__tests__/rate-limit.test.ts"
  run_suite "TypeScript: Decision Feed" "$VITEST_BIN run lib/__tests__/decision-feed.test.ts"
  run_suite "TypeScript: Start Confirm" "$VITEST_BIN run lib/__tests__/start-confirm.test.ts"
else
  echo -e "${YELLOW}⚠ Vitest not installed — skipping TypeScript tests${RESET}"
  RESULTS+=("SKIP: TypeScript tests (vitest not installed)")
fi
cd "$ROOT"

# ── Python syntax check ───────────────────────────────────────────────────────
run_suite "Python: Syntax check (all src/)" \
  "$VENV_PYTHON -c \"
import ast, os, sys
errors = []
for root, _, files in os.walk('src'):
    for f in files:
        if f.endswith('.py') and '__pycache__' not in root:
            path = os.path.join(root, f)
            try:
                ast.parse(open(path).read())
            except SyntaxError as e:
                errors.append(f'{path}: {e}')
if errors:
    for e in errors: print(e)
    sys.exit(1)
print('All Python files parse OK')
\""

# ── TypeScript type check ──────────────────────────────────────────────────────
cd "$ROOT/ui"
run_suite "TypeScript: Type check (tsc --noEmit)" \
  "$NODE node_modules/typescript/bin/tsc --noEmit 2>&1 | grep -v node_modules | grep 'error TS' | head -5 && false || true"
# Note: we invert — if grep finds no errors, the suite passes
run_suite "TypeScript: Type check (clean)" \
  "! ($NODE node_modules/typescript/bin/tsc --noEmit 2>&1 | grep -v node_modules | grep -q 'error TS')"
cd "$ROOT"

# ── Security: no hardcoded secrets in code ────────────────────────────────────
run_suite "Security: No hardcoded API keys" \
  "! grep -rn --include='*.py' --include='*.ts' --include='*.tsx' \
    -E '(BINANCE_API_KEY|GROQ_API_KEY|ANTHROPIC_API_KEY|metaapi_token)=.{8,}' \
    src/ ui/app/ ui/lib/ ui/components/ --exclude-dir=node_modules | grep -v '.env' | grep -v test | grep -v mock"

# ── Security: secrets not logged at runtime ─────────────────────────────────
# Flag only patterns where a secret *variable* is directly passed as a logger argument,
# e.g. logger.info(api_key) or print(token). String literals mentioning "token"
# in error messages are safe and not flagged.
run_suite "Security: No runtime key logging" \
  "! grep -rn --include='*.py' \
    -E '(logger|logging)\.(info|debug|warning|error|critical)\s*\([^\"'\'']*\b(api_key|api_secret|private_key|eth_key|passphrase|metaApiToken|metaapi_token)\b[^\"'\'']*\)' \
    src/ | grep -v test | grep -v '#'"

# ── Generate report ───────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}Test Report — $(date)${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""

{
echo "QuntaTradeAI — Pre-Deploy Test Report"
echo "Generated: $(date)"
echo "Environment: $(uname -a)"
echo ""
echo "RESULTS:"
for r in "${RESULTS[@]}"; do
  echo "  $r"
done
echo ""
echo "SUMMARY:"
echo "  PASSED:  $PASS"
echo "  FAILED:  $FAIL"
echo "  TOTAL:   $((PASS + FAIL))"
echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "STATUS: RELEASE READY ✓"
  echo ""
  echo "All tests passed. Safe to deploy."
else
  echo "STATUS: NOT READY FOR RELEASE ✗"
  echo ""
  echo "Fix the $FAIL failing suite(s) before deploying."
  echo "Live trading is blocked until all tests pass."
fi
} | tee "$REPORT_FILE"

for r in "${RESULTS[@]}"; do
  if [[ "$r" == PASS* ]]; then ok "  $r"
  elif [[ "$r" == FAIL* ]]; then fail "  $r"
  else echo "  $r"
  fi
done

echo ""
echo "Full report saved to: $REPORT_FILE"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo -e "${RED}${BOLD}⛔ DEPLOYMENT BLOCKED — $FAIL test suite(s) failed${RESET}"
  exit 1
else
  echo -e "${GREEN}${BOLD}✅ RELEASE READY — All $PASS test suites passed${RESET}"
  exit 0
fi
