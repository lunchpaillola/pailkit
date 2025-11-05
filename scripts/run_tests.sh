#!/bin/bash
cd api
if [ -f venv/bin/pytest ]; then
    PYTHONPATH=. venv/bin/pytest tests/test_rooms.py tests/test_transcribe.py -v
elif command -v python3.12 &> /dev/null; then
    PYTHONPATH=. python3.12 -m pytest tests/test_rooms.py tests/test_transcribe.py -v
else
    PYTHONPATH=. python -m pytest tests/test_rooms.py tests/test_transcribe.py -v
fi
