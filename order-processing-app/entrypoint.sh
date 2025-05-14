#!/bin/sh
set -e

echo "Entrypoint: PORT is $PORT" # For debugging
exec gunicorn --workers 2 --bind "0.0.0.0:$PORT" app:app