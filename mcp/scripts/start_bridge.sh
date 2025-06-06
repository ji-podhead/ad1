#!/bin/bash
PYTHON_MAIN_SCRIPT="mcp_bridge/main.py" # Path to the main Python script within the app directory
echo "    Running $PYTHON_MAIN_SCRIPT with uv..."
cd MCP-Bridge-main
uv sync
uv run python "$PYTHON_MAIN_SCRIPT"
if [ $? -ne 0 ]; then
    echo "    ERROR: Running $PYTHON_MAIN_SCRIPT with uv failed. Aborting."
    exit 1
fi
echo "----------> MCP-Bridge started successfully <----------"

exit 0 # Explicitly exit with success