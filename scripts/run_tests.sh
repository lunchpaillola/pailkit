#!/bin/bash
# Run from project root directory
if command -v python3.12 &> /dev/null; then
    python3.12 -m pytest api/tests/test_rooms.py api/tests/test_transcribe.py -v
else
    python3 -m pytest api/tests/test_rooms.py api/tests/test_transcribe.py -v
fi
