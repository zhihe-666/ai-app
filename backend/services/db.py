"""
SQLite 持久化层：用户 LLM 全局配置 + 飞书 Token + 项目数据
"""
import os
import sqlite3
from typing import Optional

# 数据库路径：项目根目录下的 data/ 目录
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
DB_PATH = os.path.join(DATA_DIR, 'app.db')


def get_db() -> sqlite3.Connection:
    """获取当前请求的数据库连接（复用 Flask g 对象）"""
    from flask import g
    if 'db' not in g:
        g.db = _connect()
    return g.db


def _connect() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def close_db(exception=None):
    """关闭数据库连接（Flask teardown 使用）"""
    from flask import g
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """初始化数据库表结构"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = _connect()
    try:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                provider_name TEXT NOT NULL DEFAULT '',
                api_key TEXT NOT NULL DEFAULT '',
                base_url TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                git_token TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS feishu_tokens (
                open_id TEXT PRIMARY KEY,
                user_name TEXT NOT NULL DEFAULT '',
                access_token TEXT NOT NULL DEFAULT '',
                refresh_token TEXT NOT NULL DEFAULT '',
                expires_at REAL NOT NULL DEFAULT 0,
                device_code TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS repo_cache (
                repo_url TEXT PRIMARY KEY,
                branch TEXT NOT NULL DEFAULT 'master',
                frontend_paths TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS commit_cache (
                repo_url TEXT NOT NULL,
                branch TEXT NOT NULL DEFAULT '',
                start_time TEXT NOT NULL DEFAULT '',
                end_time TEXT NOT NULL DEFAULT '',
                base_commit TEXT NOT NULL DEFAULT '',
                target_commit TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (repo_url, branch, start_time, end_time)
            )
        ''')
        conn.commit()
    finally:
        conn.close()


# ── LLM 用户配置 ──


def get_user_config() -> Optional[dict]:
    """获取用户已保存的 LLM 配置"""
    conn = get_db()
    row = conn.execute('SELECT * FROM user_config WHERE id = 1').fetchone()
    if row:
        return dict(row)
    return None


def save_user_config(provider_name: str, api_key: str, base_url: str, model: str, git_token: str = "") -> dict:
    """保存（或更新）用户 LLM 配置"""
    conn = get_db()
    conn.execute('''
        INSERT INTO user_config (id, provider_name, api_key, base_url, model, git_token, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            provider_name = excluded.provider_name,
            api_key = excluded.api_key,
            base_url = excluded.base_url,
            model = excluded.model,
            git_token = excluded.git_token,
            updated_at = CURRENT_TIMESTAMP
    ''', (provider_name, api_key, base_url, model, git_token))
    conn.commit()
    return {
        'provider_name': provider_name,
        'api_key': api_key,
        'base_url': base_url,
        'model': model,
        'git_token': git_token,
    }


# ── 飞书 Token 操作 ──


def save_feishu_token(
    open_id: str,
    access_token: str,
    refresh_token: str,
    expires_in: int,
    user_name: str = "",
    device_code: str = "",
) -> dict:
    """保存/更新飞书用户 token"""
    import time
    expires_at = time.time() + expires_in
    conn = get_db()
    conn.execute('''
        INSERT INTO feishu_tokens
            (open_id, user_name, access_token, refresh_token, expires_at, device_code, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(open_id) DO UPDATE SET
            user_name = excluded.user_name,
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            expires_at = excluded.expires_at,
            device_code = excluded.device_code,
            updated_at = CURRENT_TIMESTAMP
    ''', (open_id, user_name, access_token, refresh_token, expires_at, device_code))
    conn.commit()
    return {'open_id': open_id, 'access_token': access_token, 'expires_at': expires_at}


def get_feishu_token(open_id: str) -> Optional[dict]:
    """获取指定用户的飞书 Token"""
    conn = get_db()
    row = conn.execute('SELECT * FROM feishu_tokens WHERE open_id = ?', (open_id,)).fetchone()
    return dict(row) if row else None


def get_all_feishu_tokens() -> list[dict]:
    """获取所有已授权的飞书用户 Token"""
    conn = get_db()
    rows = conn.execute('SELECT * FROM feishu_tokens ORDER BY updated_at DESC').fetchall()
    return [dict(r) for r in rows]


def delete_feishu_token(open_id: str) -> None:
    """删除指定用户的飞书 Token"""
    conn = get_db()
    conn.execute('DELETE FROM feishu_tokens WHERE open_id = ?', (open_id,))
    conn.commit()


def get_feishu_token_by_device_code(device_code: str) -> Optional[dict]:
    """通过 device_code 查找 Token"""
    conn = get_db()
    row = conn.execute('SELECT * FROM feishu_tokens WHERE device_code = ?', (device_code,)).fetchone()
    return dict(row) if row else None


# ── 仓库配置缓存 ──


def save_repo_cache(repo_url: str, branch: str, frontend_paths: list[str]) -> dict:
    """保存/更新仓库配置缓存"""
    conn = get_db()
    conn.execute('''
        INSERT INTO repo_cache (repo_url, branch, frontend_paths, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(repo_url) DO UPDATE SET
            branch = excluded.branch,
            frontend_paths = excluded.frontend_paths,
            updated_at = CURRENT_TIMESTAMP
    ''', (repo_url, branch, ','.join(frontend_paths)))
    conn.commit()
    return {'repo_url': repo_url, 'branch': branch, 'frontend_paths': frontend_paths}


def get_repo_cache(repo_url: str) -> Optional[dict]:
    """获取仓库缓存配置"""
    conn = get_db()
    row = conn.execute('SELECT * FROM repo_cache WHERE repo_url = ?', (repo_url,)).fetchone()
    if row:
        d = dict(row)
        if d.get('frontend_paths'):
            d['frontend_paths'] = d['frontend_paths'].split(',')
        return d
    return None


def save_commit_cache(repo_url: str, branch: str, start_time: str, end_time: str, base_commit: str, target_commit: str) -> dict:
    """保存 commit 解析结果缓存"""
    conn = get_db()
    conn.execute('''
        INSERT INTO commit_cache (repo_url, branch, start_time, end_time, base_commit, target_commit, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(repo_url, branch, start_time, end_time) DO UPDATE SET
            base_commit = excluded.base_commit,
            target_commit = excluded.target_commit,
            updated_at = CURRENT_TIMESTAMP
    ''', (repo_url, branch, start_time, end_time, base_commit, target_commit))
    conn.commit()
    return {'repo_url': repo_url, 'base_commit': base_commit, 'target_commit': target_commit}


def get_commit_cache(repo_url: str, branch: str, start_time: str, end_time: str) -> Optional[dict]:
    """获取已缓存的 commit 解析结果"""
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM commit_cache WHERE repo_url = ? AND branch = ? AND start_time = ? AND end_time = ?',
        (repo_url, branch, start_time, end_time)
    ).fetchone()
    return dict(row) if row else None