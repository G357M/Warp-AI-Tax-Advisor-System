#!/bin/bash
# Setup cron job for daily incremental scraping
# This script should be run on the Hetzner server

echo "Setting up cron job for InfoHub scraper..."

# Create cron wrapper script
cat > /root/infohub/run_scraper.sh << 'EOF'
#!/bin/bash
# Daily scraper runner for InfoHub vector database

set -e

# Configuration
MAX_PAGES=50
LOG_DIR="/root/infohub/logs"
CONTAINER_NAME="infohub-backend-1"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Log file for this run
LOG_FILE="$LOG_DIR/scraper_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Starting scraper at $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Run scraper inside backend container
docker exec "$CONTAINER_NAME" python /app/scripts/populate_vector_db.py \
    --start-url "https://infohub.rs.ge/ka" \
    --max-pages $MAX_PAGES \
    --max-depth 2 \
    2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

echo "========================================" | tee -a "$LOG_FILE"
echo "Scraper finished at $(date)" | tee -a "$LOG_FILE"
echo "Exit code: $EXIT_CODE" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Keep only last 30 days of logs
find "$LOG_DIR" -name "scraper_*.log" -mtime +30 -delete

exit $EXIT_CODE
EOF

# Make wrapper executable
chmod +x /root/infohub/run_scraper.sh

# Add cron job (runs daily at 3:00 AM)
CRON_JOB="0 3 * * * /root/infohub/run_scraper.sh >> /root/infohub/logs/cron.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "run_scraper.sh"; then
    echo "Cron job already exists"
else
    # Add to crontab
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Cron job added successfully!"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Cron schedule: Daily at 3:00 AM"
echo "Max pages per run: 50"
echo "Logs location: /root/infohub/logs/"
echo ""
echo "To view current crontab:"
echo "  crontab -l"
echo ""
echo "To test the scraper manually:"
echo "  /root/infohub/run_scraper.sh"
echo ""
echo "To remove the cron job:"
echo "  crontab -e  # then delete the line with run_scraper.sh"
echo ""
