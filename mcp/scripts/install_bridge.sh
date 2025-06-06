#!/bin/bash

ZIP_FILE_AS="MCP-Bridge-main.zip" # How we name the downloaded file
DOWNLOAD_URL="https://github.com/SecretiveShell/MCP-Bridge/archive/refs/heads/master.zip"
EXTRACTED_DIR_FROM_ZIP="MCP-Bridge-master" # Directory name after extracting the zip from the master branch
TARGET_APP_DIR="MCP-Bridge-main"      # The final desired name for the application directory
PYTHON_MAIN_SCRIPT="mcp_bridge/main.py" # Path to the main Python script within the app directory

# Update package lists


# Upgrade pip and install uv
python3 -m pip install --upgrade pip
python3 -m pip install uv

# Attempt to download the zip file if it doesn't exist locally
# -nc: no-clobber, won't download if the file already exists.
# -O: specifies the output file name.
wget -nc -O "./$ZIP_FILE_AS" "$DOWNLOAD_URL"

# List directory contents for verification
ls -l

# Check if the ZIP file exists (either pre-existing or just downloaded)
if [ -f "./$ZIP_FILE_AS" ]; then
    echo "    $ZIP_FILE_AS exists, proceeding with setup..."

    echo "    Cleaning up old directories (if any)..."
    # Remove the original extracted directory and the target directory to ensure a clean state
    rm -rf "./$EXTRACTED_DIR_FROM_ZIP" "./$TARGET_APP_DIR"

    echo "    Unzipping $ZIP_FILE_AS..."
    # -q for "quiet" (less output), -o to overwrite files without prompting.
    # This will extract to a directory named $EXTRACTED_DIR_FROM_ZIP.
    unzip -q -o "./$ZIP_FILE_AS"
    if [ $? -ne 0 ]; then # Checks the exit code of the last command (unzip)
        echo "    ERROR: Unzipping $ZIP_FILE_AS failed. Aborting."
        exit 1
    fi

    # Verify that the expected directory exists after unzipping
    if [ ! -d "./$EXTRACTED_DIR_FROM_ZIP" ]; then
        echo "    ERROR: Expected directory './$EXTRACTED_DIR_FROM_ZIP' not found after unzipping."
        echo "    Contents of the current directory:"
        ls -A # Also shows hidden files
        exit 1
    fi

    echo "    Renaming ./$EXTRACTED_DIR_FROM_ZIP to ./$TARGET_APP_DIR..."
    mv "./$EXTRACTED_DIR_FROM_ZIP" "./$TARGET_APP_DIR"
    if [ $? -ne 0 ]; then
        echo "    ERROR: Renaming directory failed. Aborting."
        exit 1
    fi

    echo "    Changing to directory ./$TARGET_APP_DIR..."
    cd "./$TARGET_APP_DIR"
    if [ $? -ne 0 ]; then
        echo "    ERROR: Changing to directory ./$TARGET_APP_DIR failed. Aborting."
        exit 1
    fi
    echo "    Current working directory: $(pwd)"

    # echo "    Syncing Python dependencies with uv..."
    # uv sync
    # if [ $? -ne 0 ]; then
    #     echo "    ERROR: 'uv sync' failed. Aborting."
    #     exit 1
    # fi

    # echo "    Running $PYTHON_MAIN_SCRIPT with uv..."
    # uv run python "$PYTHON_MAIN_SCRIPT"
    # if [ $? -ne 0 ]; then
    #     echo "    ERROR: Running $PYTHON_MAIN_SCRIPT with uv failed. Aborting."
    #     exit 1
    # fi

    # echo "----------> MCP-Bridge started successfully <----------"
else
    echo "ERROR: $ZIP_FILE_AS was not found after wget attempt and is required. Cannot continue."
    exit 1
fi

exit 0 # Explicitly exit with success