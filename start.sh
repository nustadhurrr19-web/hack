#!/bin/bash
# 1. Start the brain in the background
python fetcher.py &

# 2. Start the web server with a LONG timeout (600 seconds)
# We use 1 worker and 4 threads to handle the user + background tasks smoothly
gunicorn server:app --bind 0.0.0.0:$PORT --timeout 600 --workers 1 --threads 4
