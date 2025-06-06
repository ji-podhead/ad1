#!/bin/bash
REPO_USER="GongRzhe"
REPO_NAME="Gmail-MCP-Server"
BRANCH_NAME="main" # Assume 'main' is the primary branch. Verify this in the repo if necessary.
ZIP_FILE_AS="${REPO_NAME}-${BRANCH_NAME}.zip" # e.g., mcp-headless-gmail-main.zip
DOWNLOAD_URL="https://github.com/${REPO_USER}/${REPO_NAME}/archive/refs/heads/${BRANCH_NAME}.zip"
EXTRACTED_DIR_FROM_ZIP="${REPO_NAME}-${BRANCH_NAME}" # e.g., mcp-headless-gmail-main
TARGET_INSTALL_DIR="${EXTRACTED_DIR_FROM_ZIP}"
echo ">>> Starting installation of ${REPO_NAME}..."
echo ">>> Installing necessary tools (wget, unzip), if not present..."
apt-get install -y wget unzip # python3-pip should already be installed from the previous script
echo ">>> Attempting to download ${DOWNLOAD_URL} as ${ZIP_FILE_AS} (if not present)..."
wget -nc -O "./${ZIP_FILE_AS}" "${DOWNLOAD_URL}"
if [ -f "./${ZIP_FILE_AS}" ]; then
    echo "    ${ZIP_FILE_AS} exists, proceeding with installation..."

    echo "    Cleaning up old directory ${TARGET_INSTALL_DIR} (if present)..."
    rm -rf "./${TARGET_INSTALL_DIR}" # Removes the target directory for a clean extraction

    echo "    Unzipping ${ZIP_FILE_AS}..."
    unzip -q -o "./${ZIP_FILE_AS}" # -q for quiet, -o to overwrite
    if [ $? -ne 0 ]; then
        echo "    ERROR: Unzipping ${ZIP_FILE_AS} failed. Aborting."
        exit 1
    fi

    if [ ! -d "./${TARGET_INSTALL_DIR}" ]; then
        echo "    ERROR: Expected directory './${TARGET_INSTALL_DIR}' not found after unzipping."
        echo "    Contents of the current directory:"
        ls -A # Shows hidden files as well
        exit 1
    fi

    echo "    Installing ./${TARGET_INSTALL_DIR} in editable mode..."
    mkdir "${HOME}/gmail-mcp/"
    npm install --prefix "./${TARGET_INSTALL_DIR}"
    npm run build --prefix "./${TARGET_INSTALL_DIR}"
    ls "./${TARGET_INSTALL_DIR}"
    cp -r "./${TARGET_INSTALL_DIR}/dist" "${HOME}/gmail-mcp/"
    ls  "${HOME}/gmail-mcp/"
    echo "----------> ${REPO_NAME} installed successfully <----------"
else
    echo "ERROR: ${ZIP_FILE_AS} was not found after wget attempt and is required. Cannot continue."
    exit 1
fi
