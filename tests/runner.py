#!/usr/bin/env python3
"""
RFP Response Assistant — Master Opaque-Box Test Runner
Executes Tiers 1 through 4 across all features F01 through F27.
Usage:
    python3 tests/runner.py
    python3 tests/runner.py --tier 1
    python3 tests/runner.py --tier 2
    python3 tests/runner.py --tier 3
    python3 tests/runner.py --tier 4
    python3 tests/runner.py --url http://localhost:8000/api
    python3 tests/runner.py --verbose
    python3 tests/runner.py --json-report results.json
"""

import argparse
import json
import os
import sys
import time
import unittest
from typing import Dict, List, Optional, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# Terminal ANSI Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


TIER_MAPPING = {
    "1": {
        "name": "Tier 1: Feature Coverage (F01-F27)",
        "dir": "tests/tier1_features",
        "desc": ">=5 test cases per core feature across ingestion, classification, RAG, pricing, notes, questions, export, settings, services, tracker",
    },
    "2": {
        "name": "Tier 2: Boundary & Corner Cases",
        "dir": "tests/tier2_boundaries",
        "desc": "Ambiguous classification, empty KB, missing pricing, won vs lost biasing, notes permutations, mock export flags",
    },
    "3": {
        "name": "Tier 3: Cross-Feature Combinations",
        "dir": "tests/tier3_combinations",
        "desc": "Tripartite notes+RAG+pricing synthesis, open question resolution loop, selective export comments, settings propagation, cascading",
    },
    "4": {
        "name": "Tier 4: Real-World Application Scenario",
        "dir": "tests/tier4_realworld",
        "desc": "Automated 10-step simulation of the manual walkthrough script using National Heritage Trust sample RFP",
    },
}


class CustomTestResult(unittest.TestResult):
    def __init__(self, verbose: bool = False):
        super().__init__()
        self.verbose = verbose
        self.test_records: List[Dict[str, Any]] = []

    def startTest(self, test):
        super().startTest(test)
        if self.verbose:
            test_name = f"{test.__class__.__name__}.{test._testMethodName}"
            sys.stdout.write(f"  • {test_name:<65} ")
            sys.stdout.flush()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.test_records.append({
            "test": f"{test.__class__.__name__}.{test._testMethodName}",
            "status": "PASS",
            "message": "",
        })
        if self.verbose:
            sys.stdout.write(f"{GREEN}[PASS]{RESET}\n")
            sys.stdout.flush()

    def addFailure(self, test, err):
        super().addFailure(test, err)
        msg = self._exc_info_to_string(err, test)
        self.test_records.append({
            "test": f"{test.__class__.__name__}.{test._testMethodName}",
            "status": "FAIL",
            "message": msg,
        })
        if self.verbose:
            sys.stdout.write(f"{RED}[FAIL]{RESET}\n")
            sys.stdout.flush()

    def addError(self, test, err):
        super().addError(test, err)
        msg = self._exc_info_to_string(err, test)
        self.test_records.append({
            "test": f"{test.__class__.__name__}.{test._testMethodName}",
            "status": "ERROR",
            "message": msg,
        })
        if self.verbose:
            sys.stdout.write(f"{RED}[ERROR]{RESET}\n")
            sys.stdout.flush()


def run_tier(tier_key: str, verbose: bool = False) -> Tuple[int, int, int, float, List[Dict]]:
    meta = TIER_MAPPING[tier_key]
    tier_dir = os.path.join(PROJECT_ROOT, meta["dir"])

    print(f"\n{BOLD}{BLUE}======================================================================{RESET}")
    print(f"{BOLD}  Running {meta['name']}{RESET}")
    print(f"  Scope: {meta['desc']}")
    print(f"{BOLD}{BLUE}======================================================================{RESET}")

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=tier_dir, pattern="test_*.py")

    start_time = time.time()
    result = CustomTestResult(verbose=verbose)
    suite.run(result)
    elapsed = time.time() - start_time

    passes = len(result.test_records) - len(result.failures) - len(result.errors)
    failures = len(result.failures)
    errors = len(result.errors)

    if not verbose:
        for r in result.test_records:
            status_str = f"{GREEN}PASS{RESET}" if r["status"] == "PASS" else f"{RED}{r['status']}{RESET}"
            print(f"  [{status_str}] {r['test']}")

    # Print failures if any
    if result.failures or result.errors:
        print(f"\n{RED}{BOLD}Failures and Errors:{RESET}")
        for test, trace in result.failures + result.errors:
            print(f"{RED}--- {test} ---{RESET}")
            print(trace)

    print(f"{BOLD}Subtotal:{RESET} {passes} passed, {failures} failed, {errors} errors in {elapsed:.3f}s\n")
    return passes, failures, errors, elapsed, result.test_records


def main():
    parser = argparse.ArgumentParser(description="Master Test Runner for RFP Response Assistant")
    parser.add_argument(
        "--tier", "-t",
        choices=["1", "2", "3", "4", "all"],
        default="all",
        help="Specify which tier to execute (default: all)",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000/api",
        help="Base URL of live backend if running (default: http://localhost:8000/api)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output per test method",
    )
    parser.add_argument(
        "--json-report",
        help="Path to write structured JSON test report",
    )
    args = parser.parse_args()

    # Pass configuration to harness via environment variable if specified
    if args.url:
        os.environ["RFP_API_BASE_URL"] = args.url

    tiers_to_run = ["1", "2", "3", "4"] if args.tier == "all" else [args.tier]

    print(f"\n{BOLD}{YELLOW}╔════════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{YELLOW}║        RFP RESPONSE ASSISTANT — E2E TEST RUNNER       ║{RESET}")
    print(f"{BOLD}{YELLOW}╚════════════════════════════════════════════════════════════════════╝{RESET}")
    print(f"Environment: {sys.executable} (Python {sys.version.split()[0]})")
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Target Mode: Live HTTP check ({args.url}) with auto-fallback to Contract Engine")
    print(f"Tiers Scheduled: {', '.join(tiers_to_run)}")

    overall_passes = 0
    overall_failures = 0
    overall_errors = 0
    total_start = time.time()
    tier_summaries = {}
    all_records = []

    for t in tiers_to_run:
        p, f, e, el, recs = run_tier(t, verbose=args.verbose)
        overall_passes += p
        overall_failures += f
        overall_errors += e
        tier_summaries[t] = {
            "tier": t,
            "name": TIER_MAPPING[t]["name"],
            "passed": p,
            "failed": f,
            "errors": e,
            "elapsed_seconds": round(el, 3),
        }
        all_records.extend(recs)

    total_elapsed = time.time() - total_start
    total_tests = overall_passes + overall_failures + overall_errors

    print(f"\n{BOLD}{BLUE}======================================================================{RESET}")
    print(f"{BOLD}                        MASTER TEST SUMMARY                           {RESET}")
    print(f"{BOLD}{BLUE}======================================================================{RESET}")
    for t, summ in tier_summaries.items():
        status_badge = f"{GREEN}ALL PASSED{RESET}" if summ["failed"] == 0 and summ["errors"] == 0 else f"{RED}FAILURES DETECTED{RESET}"
        print(f"  • {summ['name']:<42} {summ['passed']:>3} passed  {summ['failed']:>2} failed  [{status_badge}]")

    print(f"{BOLD}{BLUE}----------------------------------------------------------------------{RESET}")
    print(f"  {BOLD}Total Tests Run:{RESET}      {total_tests}")
    print(f"  {BOLD}Passed:{RESET}               {GREEN}{overall_passes}{RESET}")
    print(f"  {BOLD}Failed:{RESET}               {RED if overall_failures > 0 else GREEN}{overall_failures}{RESET}")
    print(f"  {BOLD}Errors:{RESET}               {RED if overall_errors > 0 else GREEN}{overall_errors}{RESET}")
    print(f"  {BOLD}Total Execution Time:{RESET} {total_elapsed:.3f}s")
    print(f"{BOLD}{BLUE}======================================================================{RESET}\n")

    if args.json_report:
        report_data = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_tests": total_tests,
            "passed": overall_passes,
            "failed": overall_failures,
            "errors": overall_errors,
            "execution_time_seconds": round(total_elapsed, 3),
            "tier_summaries": tier_summaries,
            "test_records": all_records,
        }
        with open(args.json_report, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        print(f"Report written to: {args.json_report}\n")

    if overall_failures > 0 or overall_errors > 0:
        print(f"{RED}{BOLD}OVERALL VERIFICATION STATUS: FAILED{RESET}\n")
        sys.exit(1)
    else:
        print(f"{GREEN}{BOLD}OVERALL VERIFICATION STATUS: 100% PASSED{RESET}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
