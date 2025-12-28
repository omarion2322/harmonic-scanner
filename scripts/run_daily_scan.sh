#!/bin/bash

# Daily Hybrid Harmonic Pattern Scanner
# Runs the hybrid scanner (Pyharmonics + Scott Carney) and emails/logs results

# Configuration
PROJECT_DIR="/Users/omer_le/HarmonicProject"
VENV_PATH="$PROJECT_DIR/.venv"
PYTHON_PATH="$VENV_PATH/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"
REPORT_BASE_DIR="$PROJECT_DIR/reports"

# Create directories if they don't exist
mkdir -p "$LOG_DIR"
mkdir -p "$REPORT_BASE_DIR"

# Set up logging
DATE=$(date +%Y-%m-%d)
TIME=$(date +%H-%M-%S)
LOG_FILE="$LOG_DIR/scan_${DATE}_${TIME}.log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Starting Hybrid Harmonic Pattern Scan" | tee -a "$LOG_FILE"
echo "Pyharmonics + Scott Carney Framework" | tee -a "$LOG_FILE"
echo "Date: $DATE" | tee -a "$LOG_FILE"
echo "Time: $TIME" | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Change to project directory
cd "$PROJECT_DIR" || exit 1

# Record start time
START_TIME=$(date +%s)

# Run the scanner with real-time progress logging
echo "Initializing scanner..." | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Run scanner with real-time output
# -u flag for unbuffered output, tee for both screen and log
"$PYTHON_PATH" -u src/harmonic_scanner.py 2>&1 | tee -a "$LOG_FILE"

# Check if scan was successful
if [ $? -eq 0 ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"
    echo "✓ Scan completed successfully!" | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"

    # Report is automatically saved to reports/<date>/ by the script
    REPORT_PATH="$REPORT_BASE_DIR/$DATE/harmonic_report_${DATE}.txt"
    if [ -f "$REPORT_PATH" ]; then
        echo "" | tee -a "$LOG_FILE"
        echo "Report Location:" | tee -a "$LOG_FILE"
        echo "  $REPORT_PATH" | tee -a "$LOG_FILE"

        # Extract and display summary statistics from report
        echo "" | tee -a "$LOG_FILE"
        echo "Scan Summary:" | tee -a "$LOG_FILE"
        if grep -q "Total Stocks Scanned:" "$REPORT_PATH"; then
            grep "Total Stocks Scanned:" "$REPORT_PATH" | sed 's/^/  /' | tee -a "$LOG_FILE"
            grep "BUY Signals:" "$REPORT_PATH" | sed 's/^/  /' | tee -a "$LOG_FILE"
            grep "SELL Signals:" "$REPORT_PATH" | sed 's/^/  /' | tee -a "$LOG_FILE"
            grep "HOLD Signals:" "$REPORT_PATH" | sed 's/^/  /' | tee -a "$LOG_FILE"
        fi

        # Show BUY/SELL tickers if any
        echo "" | tee -a "$LOG_FILE"
        BUY_COUNT=$(grep -c "^Ticker:" "$REPORT_PATH" 2>/dev/null || echo "0")
        if [ "$BUY_COUNT" -gt 0 ]; then
            echo "Trading Signals Found:" | tee -a "$LOG_FILE"
            grep "^Ticker:" "$REPORT_PATH" | head -5 | sed 's/^/  /' | tee -a "$LOG_FILE"
            if [ "$BUY_COUNT" -gt 5 ]; then
                echo "  ... and $(($BUY_COUNT - 5)) more (see full report)" | tee -a "$LOG_FILE"
            fi
        else
            echo "No BUY/SELL signals found in this scan" | tee -a "$LOG_FILE"
        fi
    fi

    # Extract trades for paper trading
    echo "" | tee -a "$LOG_FILE"
    echo "Extracting trades for paper trading..." | tee -a "$LOG_FILE"
    "$PYTHON_PATH" "$PROJECT_DIR/scripts/extract_trades.py" --date "$DATE" --timeframe 1wk 2>&1 | tee -a "$LOG_FILE"

    # Optional: Send email notification (requires mailx or mail command)
    # Uncomment and configure if you want email alerts
    # if [ -f "$REPORT_PATH" ]; then
    #     mail -s "Harmonic Pattern Report - $DATE" your-email@example.com < "$REPORT_PATH"
    # fi

else
    echo "" | tee -a "$LOG_FILE"
    echo "ERROR: Scan failed! Check log for details." | tee -a "$LOG_FILE"

    # Optional: Send error notification
    # echo "Harmonic scanner failed on $DATE. Check logs at $LOG_FILE" | mail -s "ERROR: Harmonic Scanner Failed" your-email@example.com
fi

echo "" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "Scan finished at $(date)" | tee -a "$LOG_FILE"

# Calculate and display elapsed time
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
MINUTES=$((ELAPSED / 60))
SECONDS=$((ELAPSED % 60))
echo "Total elapsed time: ${MINUTES}m ${SECONDS}s" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Optional: Clean up old logs and reports (keep last 30 days for logs, 90 for reports)
find "$LOG_DIR" -name "scan_*.log" -mtime +30 -delete
find "$REPORT_BASE_DIR" -type d -mtime +90 -empty -delete  # Clean up empty old report directories
find "$REPORT_BASE_DIR" -name "harmonic_report_*.txt" -mtime +90 -delete  # Clean up old hybrid reports
find "$REPORT_BASE_DIR" -name "harmonic_report_*.txt" -mtime +90 -delete  # Clean up old original reports
