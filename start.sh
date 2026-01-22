#!/bin/bash
python fetcher.py &
gunicorn server:app --bind 0.0.0.0:$PORT --timeout 600 --workers 1 --threads 4
