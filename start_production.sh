#!/bin/bash
# start_production.sh — Launch IMPACT S2S in production mode
#
# This script removes any existing database and starts fresh
# with real strategy data and the Bradley-Terry adaptive algorithm.

echo "=== IMPACT S2S — Production Mode ==="
echo ""

# Remove existing database for a clean start
rm -f wiki_survey.db
rm -f instance/wiki_survey.db
echo "✓ Cleared existing database"

# Set production mode
export SURVEY_MODE=production

# Optional: Uncomment and modify these to override defaults
# export STRATEGIES_CSV=data/Strategies.csv
# export BT_SIGMA2=1.0
# export BT_PROXY=top_heavy
# Production must set ADMIN_CODE. Do not rely on the local fallback.
# export SECRET_KEY=your-secure-random-key-here

echo "✓ SURVEY_MODE=production"
echo "✓ BT_PROXY=${BT_PROXY:-top_heavy}"
echo "✓ BT_SIGMA2=${BT_SIGMA2:-1.0}"
echo ""
echo "Starting server on http://localhost:5000"
echo "Admin portal at http://localhost:5000/admin"
echo ""

python app.py
