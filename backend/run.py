#!/usr/bin/env python3
"""启动 Flask 后端，避免 reloader 问题"""
import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from app import app

if __name__ == '__main__':
    print(f"Starting Flask on port 5000 (no reloader)...")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
