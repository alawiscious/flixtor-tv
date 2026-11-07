#!/bin/zsh
cd -- "${0:A:h}" || exit 1
echo 'FlixTor TV preview — keep this window open. Ctrl+C stops the server.'
node -e 'const os=require("os"); for(const rows of Object.values(os.networkInterfaces())) for(const a of rows||[]) if(a.family==="IPv4"&&!a.internal) console.log("TV URL: http://"+a.address+":8765/FlixTor_TV_Preview.html");'
echo 'Mac URL: http://localhost:8765/FlixTor_TV_Preview.html'
python3 -m http.server 8765 --bind 0.0.0.0
