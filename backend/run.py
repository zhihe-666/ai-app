#!/usr/bin/env python3
"""启动 Flask 后端，避免 reloader 问题"""
import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

# 加载 .env 环境变量（默认 LLM/Git 配置）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 启动时从 DB 读取已保存配置，注入环境变量作为默认兜底
# 对方未配置时也能复用本地保存的 LLM/Git 配置
try:
    import sqlite3
    from pathlib import Path
    _db_path = Path(__file__).parent / 'data' / 'app.db'
    if _db_path.exists():
        _conn = sqlite3.connect(str(_db_path))
        _conn.row_factory = sqlite3.Row
        _row = _conn.execute('SELECT * FROM user_config WHERE id = 1').fetchone()
        _conn.close()
        if _row:
            _saved = dict(_row)
            if _saved.get('api_key') and not os.environ.get('DEFAULT_API_KEY'):
                os.environ['DEFAULT_API_KEY'] = _saved['api_key']
            if _saved.get('base_url') and not os.environ.get('DEFAULT_BASE_URL'):
                os.environ['DEFAULT_BASE_URL'] = _saved['base_url']
            if _saved.get('model') and not os.environ.get('DEFAULT_MODEL'):
                os.environ['DEFAULT_MODEL'] = _saved['model']
            if _saved.get('git_token') and not os.environ.get('DEFAULT_GIT_TOKEN'):
                os.environ['DEFAULT_GIT_TOKEN'] = _saved['git_token']
            print(f"[Startup] 已加载本地默认配置: model={_saved.get('model','')}, base_url={_saved.get('base_url','')}")
except Exception as _e:
    print(f"[Startup] 加载默认配置失败（忽略）: {_e}")

from app import app

if __name__ == '__main__':
    print(f"Starting Flask on port 5000 (no reloader)...")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
