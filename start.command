#!/bin/bash
# Double-click this file to launch the Spaced Repetition app.

cd "$(dirname "$0")"

# Kill any previous instance on port 5050
lsof -ti:5050 | xargs kill -9 2>/dev/null

echo ""
echo "  Starting Spaced Repetition server..."
echo "  Opening http://localhost:5050"
echo "  Close this window to stop the server."
echo ""

python3 server.py
