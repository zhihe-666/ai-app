import sys
sys.path.insert(0, '/Users/admin/.dewuclaw/workspaces/default/coding_projects/ai-app/backend')
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s', stream=sys.stderr)

print("1: importing db", flush=True)
from services.db import init_db
print("2: init_db", flush=True)
init_db()
print("3: importing app", flush=True)
from app import app
print("4: ready, running...", flush=True)
app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)