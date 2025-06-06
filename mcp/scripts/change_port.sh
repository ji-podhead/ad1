FILE_TO_EDIT="/Gmail-MCP-Server-main/dist/index.js"
pwd
if [ ! -f "$FILE_TO_EDIT" ]; then
    echo "FEHLER: Datei '$FILE_TO_EDIT' nicht gefunden!"
    exit 1
fi

sed -i.bak 's|: "http://localhost:3000/oauth2callback"|: "https://redirectmeto.com/localhost:3000/oauth2callback"|g' "$FILE_TO_EDIT"

echo "------------------"
cat "$FILE_TO_EDIT" | grep "http"
echo "------------------"