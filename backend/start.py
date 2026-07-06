# 启动 Flask（禁用 reloader，适合后台进程）
import os, sys
sys.path.insert(0, '/Users/admin/.dewuclaw/workspaces/default/coding_projects/ai-app/backend')
from app import app
print(f"Starting on port 5000 (PID={os.getpid()})", flush=True)
app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)