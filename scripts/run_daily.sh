#!/bin/bash
# BirdsAiView — Fetch news (outputs JSON for OpenClaw)
# OpenClaw heartbeat/cron should call this and consume stdout.
# Example: output=$(python main.py --fetch-only)

set -e
cd "$(dirname "$0")/.."

python main.py --fetch-only
