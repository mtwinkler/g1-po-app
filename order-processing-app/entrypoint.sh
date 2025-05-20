#!/bin/sh
set -ex # Add -x for xtrace to see commands being executed

echo "ENTRYPOINT: Script starting."
echo "ENTRYPOINT: Current directory: $(pwd)"
echo "ENTRYPOINT: Listing /app directory contents:"
ls -la /app
echo "ENTRYPOINT: PORT environment variable is: '$PORT'"
echo "ENTRYPOINT: PYTHONPATH is: '$PYTHONPATH'"
echo "ENTRYPOINT: PATH is: '$PATH'"
echo "ENTRYPOINT: Python version: $(python --version || echo 'Failed to get Python version')"
echo "ENTRYPOINT: Attempting to get Gunicorn version..."
gunicorn --version || echo "ENTRYPOINT: gunicorn command failed or not found"
echo "ENTRYPOINT: Attempting to start Gunicorn with detailed logging..."

# Start Gunicorn with verbose logging and fewer workers for debugging
# Send Gunicorn's own logs to stdout so Cloud Run captures them
exec gunicorn \
    --workers 1 \
    --threads 2 \
    --bind "0.0.0.0:$PORT" \
    --log-level debug \
    --access-logfile '-' \
    --error-logfile '-' \
    "app:app"

# This line should ideally not be reached if exec gunicorn works
echo "ENTRYPOINT: Gunicorn exec command finished OR FAILED TO EXEC."
exit 1 # Explicitly exit with an error if exec fails to take over