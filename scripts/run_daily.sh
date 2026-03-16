#!/bin/bash
# BirdsAiView — Daily surveillance digest
# Schedule via cron: 0 7 * * * /path/to/BirdsAiView/scripts/run_daily.sh

set -e
cd "$(dirname "$0")/.."

# Run unified digest (all pipelines, one message)
python main.py --digest

# Or run pipelines individually:
# python main.py --pipeline property
# python main.py --pipeline inflation
# python main.py --pipeline ma
# python main.py --pipeline dev_projects
# python main.py --pipeline tech
# python main.py --skill job_scout
