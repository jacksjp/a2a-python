#!/usr/bin/env python3
import os
import sys
import json
import datetime
import logging
import urllib.request
import urllib.error

# Configure logging to match standard ITK formatting
logging.basicConfig(
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

def main():
    results_file = "raw_results.json"
    history_output_file = "itk_python.json"
    history_url = "https://github.com/a2aproject/a2a-python/releases/download/nightly-metrics/itk_python.json"

    if not os.path.exists(results_file):
        logger.error("Results file %s not found.", results_file)
        sys.exit(1)

    try:
        with open(results_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        logger.error("Error loading results JSON: %s", e)
        sys.exit(1)

    all_passed = data.get('all_passed', False)
    results = data.get('results', {})

    logger.info("--------------------------------------------------------")
    logger.info("ITK TEST RESULTS:")
    logger.info("--------------------------------------------------------")
    for test, passed in results.items():
        status = 'PASSED' if passed else 'FAILED'
        logger.info("%s: %s", test, status)
    logger.info("--------------------------------------------------------")
    logger.info("OVERALL STATUS: %s", 'PASSED' if all_passed else 'FAILED')
    logger.info("--------------------------------------------------------")

    # --- NIGHTLY PIPELINE HISTORY PROCESSING ---
    is_nightly_run = os.environ.get("ITK_NIGHTLY_RUN", "False").upper() == "TRUE"
    
    if is_nightly_run:
        logger.info("Nightly run detected. Fetching existing history from GitHub releases...")
        
        # 1. Fetch existing history
        try:
            req = urllib.request.Request(history_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status == 200:
                    history = json.loads(response.read().decode('utf-8'))
                    logger.info("Successfully retrieved history. Current entries: %d", len(history))
                else:
                    logger.warning("No existing history found (HTTP %d). Initializing fresh history.", response.status)
                    history = []
        except urllib.error.HTTPError as e:
            if e.code == 444 or e.code == 404:
                logger.warning("No existing history found (HTTP %d). Initializing fresh history.", e.code)
            else:
                logger.warning("HTTP error downloading existing history: %d. Initializing fresh history.", e.code)
            history = []
        except Exception as e:
            logger.warning("Failed to download existing history: %s. Initializing fresh history.", e)
            history = []

        # 2. Load full scenario definitions to compile comprehensive data
        scenarios_file = "scenarios.json"
        try:
            with open(scenarios_file, 'r') as f:
                scenarios_data = json.load(f)
            scenarios_list = scenarios_data.get('tests', [])
        except Exception as e:
            logger.warning("Failed to load scenarios.json definitions: %s", e)
            scenarios_list = []

        # Merge full definitions with pass/fail outcome
        compiled_scenarios = []
        for scenario in scenarios_list:
            name = scenario.get('name')
            passed = results.get(name, False)
            combined = dict(scenario)
            combined['passed'] = passed
            compiled_scenarios.append(combined)

        # 3. Compile new run data
        new_run = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "commit_sha": os.environ.get("GITHUB_SHA", "local-dev"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID", "0"),
            "all_passed": all_passed,
            "scenarios": compiled_scenarios
        }

        # 3. Merge and Prune
        history.append(new_run)
        
        # Keep last N entries (default to 50, configurable)
        history_limit = int(os.environ.get("ITK_HISTORY_LIMIT", "50"))
        if len(history) > history_limit:
            history = history[-history_limit:]
            logger.info("Pruned history to last %d entries.", history_limit)

        # 4. Save to disk (for upload step)
        try:
            with open(history_output_file, 'w') as f:
                json.dump(history, f, indent=2)
            logger.info("Successfully compiled and wrote nightly history to: %s", history_output_file)
        except Exception as e:
            logger.error("Error writing history file: %s", e)
            sys.exit(1)

    # Exit with non-zero code if tests failed (unless it is a nightly run)
    if not all_passed:
        if is_nightly_run:
            logger.info("Nightly run: successfully compiled metrics. Exiting with 0 to allow upload step.")
            sys.exit(0)
        sys.exit(1)

if __name__ == "__main__":
    main()
