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

        # ── PRD 智能生成系统 — 4 张表 ──
        conn.execute('''
            CREATE TABLE IF NOT EXISTS prd_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT 'simple',
                status TEXT NOT NULL DEFAULT 'init',
                user_input TEXT NOT NULL DEFAULT '',
                collected_info TEXT NOT NULL DEFAULT '{}',
                minutes_extract TEXT NOT NULL DEFAULT '{}',
                current_round INTEGER NOT NULL DEFAULT 0,
                completeness REAL NOT NULL DEFAULT 0.0,
                outline TEXT NOT NULL DEFAULT '[]',
                section_contents TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS prd_versions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                section TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                version_num INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS prd_files (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                filename TEXT NOT NULL DEFAULT '',
                file_type TEXT NOT NULL DEFAULT 'temporary',
                storage_path TEXT NOT NULL DEFAULT '',
                text_content TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS prd_chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'system',
                content TEXT NOT NULL DEFAULT '',
                round INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_prd_versions_session
            ON prd_versions (session_id, section, version_num)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_prd_messages_session
            ON prd_chat_messages (session_id, round)
        ''')

        # ── 知识库问答历史 ──
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                query TEXT NOT NULL DEFAULT '',
                answer TEXT NOT NULL DEFAULT '',
                sources TEXT NOT NULL DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_chat_sessions_created
            ON chat_sessions (created_at DESC)
        ''')

        # ── Schema migration：给旧表补缺失列（CREATE TABLE IF NOT EXISTS 不改已存在的表）──
        def _has_column(table: str, col: str) -> bool:
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()]
            return col in cols

        if not _has_column('user_config', 'git_token'):
            conn.execute('ALTER TABLE user_config ADD COLUMN git_token TEXT NOT NULL DEFAULT \'\'')
            print('[DB] migration: user_config 新增 git_token 列')

        # PRD 深度模式：状态机阶段 + 各 Agent 产出（JSON）
        if not _has_column('prd_sessions', 'deep_state'):
            conn.execute('ALTER TABLE prd_sessions ADD COLUMN deep_state TEXT NOT NULL DEFAULT \'init\'')
            print('[DB] migration: prd_sessions 新增 deep_state 列')
        if not _has_column('prd_sessions', 'deep_artifacts'):
            conn.execute('ALTER TABLE prd_sessions ADD COLUMN deep_artifacts TEXT NOT NULL DEFAULT \'{}\'')
            print('[DB] migration: prd_sessions 新增 deep_artifacts 列')
        # 飞书文档导出 URL（export_to_feishu 已用，旧库可能缺）
        if not _has_column('prd_sessions', 'feishu_doc_url'):
            conn.execute('ALTER TABLE prd_sessions ADD COLUMN feishu_doc_url TEXT NOT NULL DEFAULT \'\'')
            print('[DB] migration: prd_sessions 新增 feishu_doc_url 列')

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


# ── PRD 智能生成系统 — CRUD ──

import uuid
import json


def _now() -> str:
    """返回当前时间戳字符串"""
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ── prd_sessions ──


def create_prd_session(mode: str, user_input: str) -> dict:
    """创建 PRD 会话"""
    session_id = str(uuid.uuid4())
    conn = get_db()
    conn.execute('''
        INSERT INTO prd_sessions (id, mode, user_input, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (session_id, mode, user_input, _now(), _now()))
    conn.commit()
    return get_prd_session(session_id)


def get_prd_session(session_id: str) -> dict | None:
    """获取 PRD 会话"""
    conn = get_db()
    row = conn.execute('SELECT * FROM prd_sessions WHERE id = ?', (session_id,)).fetchone()
    return dict(row) if row else None


def update_prd_session(session_id: str, **kwargs) -> dict | None:
    """更新 PRD 会话字段

    仅更新传入的 kwargs 中非空的字段。
    collected_info / minutes_extract / outline / section_contents 自动 JSON 序列化。

    Usage:
        update_prd_session('xxx', status='writing', completeness=0.8)
        update_prd_session('xxx', outline=json.dumps(sections))
    """
    if not kwargs:
        return get_prd_session(session_id)

    # JSON 序列化
    for json_field in ('collected_info', 'minutes_extract', 'outline', 'section_contents', 'deep_artifacts'):
        val = kwargs.get(json_field)
        if val is not None and isinstance(val, (dict, list)):
            kwargs[json_field] = json.dumps(val, ensure_ascii=False)

    fields = ', '.join(f'{k} = ?' for k in kwargs)
    values = list(kwargs.values())

    conn = get_db()
    conn.execute(
        f'UPDATE prd_sessions SET {fields}, updated_at = ? WHERE id = ?',
        (*values, _now(), session_id)
    )
    conn.commit()
    return get_prd_session(session_id)


# ── prd_versions ──


def get_next_version_num(session_id: str, section: str) -> int:
    """获取指定章节下一个版本号"""
    conn = get_db()
    row = conn.execute(
        'SELECT COALESCE(MAX(version_num), 0) + 1 AS next_ver FROM prd_versions WHERE session_id = ? AND section = ?',
        (session_id, section)
    ).fetchone()
    return row['next_ver'] if row else 1


def save_prd_version(session_id: str, section: str, content: str) -> dict:
    """保存章节版本快照

    自动生成版本号并保留最近 3 个版本。
    """
    version_id = str(uuid.uuid4())
    version_num = get_next_version_num(session_id, section)
    conn = get_db()
    conn.execute('''
        INSERT INTO prd_versions (id, session_id, section, content, version_num, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (version_id, session_id, section, content, version_num, _now()))
    conn.commit()

    # 清理：只保留该章节最近 3 个版本
    cleanup_old_versions(session_id, section, keep=3)

    return {'id': version_id, 'version_num': version_num}


def get_prd_versions(session_id: str, section: str | None = None) -> list[dict]:
    """获取版本列表

    Args:
        session_id: 会话 ID
        section: 可选，指定章节
    """
    conn = get_db()
    if section:
        rows = conn.execute(
            'SELECT id, session_id, section, version_num, created_at FROM prd_versions '
            'WHERE session_id = ? AND section = ? ORDER BY version_num DESC',
            (session_id, section)
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT id, session_id, section, version_num, created_at FROM prd_versions '
            'WHERE session_id = ? ORDER BY section, version_num DESC',
            (session_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_prd_version_content(version_id: str) -> dict | None:
    """获取指定版本的内容"""
    conn = get_db()
    row = conn.execute('SELECT * FROM prd_versions WHERE id = ?', (version_id,)).fetchone()
    return dict(row) if row else None


def cleanup_old_versions(session_id: str, section: str, keep: int = 3):
    """清理多余的旧版本

    保留最近 keep 个版本，删除更旧的。
    """
    conn = get_db()
    conn.execute('''
        DELETE FROM prd_versions WHERE id IN (
            SELECT id FROM prd_versions
            WHERE session_id = ? AND section = ?
            ORDER BY version_num DESC
            LIMIT -1 OFFSET ?
        )
    ''', (session_id, section, keep))
    conn.commit()


# ── prd_files ──


def save_prd_file(
    file_id: str, session_id: str, filename: str,
    file_type: str, storage_path: str, text_content: str,
) -> dict:
    """保存上传的文件记录"""
    conn = get_db()
    conn.execute('''
        INSERT INTO prd_files (id, session_id, filename, file_type, storage_path, text_content, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (file_id, session_id, filename, file_type, storage_path, text_content, _now()))
    conn.commit()
    return {'id': file_id, 'filename': filename, 'file_type': file_type}


def get_prd_files(session_id: str) -> list[dict]:
    """获取会话关联的文件列表"""
    conn = get_db()
    rows = conn.execute(
        'SELECT id, filename, file_type, created_at FROM prd_files WHERE session_id = ? ORDER BY created_at DESC',
        (session_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_prd_file(file_id: str) -> dict | None:
    """获取单个文件详情"""
    conn = get_db()
    row = conn.execute('SELECT * FROM prd_files WHERE id = ?', (file_id,)).fetchone()
    return dict(row) if row else None


# ── prd_chat_messages ──


def add_chat_message(session_id: str, role: str, content: str, round_num: int) -> dict:
    """添加对话消息

    Args:
        session_id: 会话 ID
        role: 'system' | 'user'
        content: 消息内容
        round_num: 对话轮次
    """
    msg_id = str(uuid.uuid4())
    conn = get_db()
    conn.execute('''
        INSERT INTO prd_chat_messages (id, session_id, role, content, round, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (msg_id, session_id, role, content, round_num, _now()))
    conn.commit()
    return {'id': msg_id, 'role': role, 'round': round_num}


def get_chat_messages(session_id: str) -> list[dict]:
    """获取会话的对话历史（按轮次正序）"""
    conn = get_db()
    rows = conn.execute(
        'SELECT id, session_id, role, content, round, created_at FROM prd_chat_messages '
        'WHERE session_id = ? ORDER BY round ASC, created_at ASC',
        (session_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ── chat_sessions（知识库问答历史）──


def save_chat_session(query: str, answer: str, sources: list) -> dict:
    """保存一条知识库问答历史

    Args:
        query: 用户问题
        answer: LLM 完整回答
        sources: 引用来源列表
    Returns:
        dict: {id, title, created_at}

    Note: 直接建独立连接，不依赖 Flask g 对象（流式 generator 在请求上下文外执行，g 失效）。
    """
    session_id = str(uuid.uuid4())
    # title 取 query 前 30 字
    title = query[:30] + ('…' if len(query) > 30 else '')
    conn = _connect()
    try:
        conn.execute('''
            INSERT INTO chat_sessions (id, title, query, answer, sources, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, title, query, answer, json.dumps(sources, ensure_ascii=False), _now()))
        conn.commit()
    finally:
        conn.close()
    return {'id': session_id, 'title': title, 'created_at': _now()}


def list_chat_sessions(limit: int = 50) -> list[dict]:
    """列出问答历史（按时间倒序）"""
    conn = get_db()
    rows = conn.execute(
        'SELECT id, title, query, created_at FROM chat_sessions '
        'ORDER BY created_at DESC, id DESC LIMIT ?',
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_chat_session(session_id: str) -> dict | None:
    """获取单条问答历史详情（含 answer 和 sources）"""
    conn = get_db()
    row = conn.execute(
        'SELECT id, title, query, answer, sources, created_at FROM chat_sessions WHERE id = ?',
        (session_id,)
    ).fetchone()
    if row:
        d = dict(row)
        try:
            d['sources'] = json.loads(d.get('sources') or '[]')
        except json.JSONDecodeError:
            d['sources'] = []
        return d
    return None


def delete_chat_session(session_id: str) -> bool:
    """删除单条问答历史"""
    conn = get_db()
    cur = conn.execute('DELETE FROM chat_sessions WHERE id = ?', (session_id,))
    conn.commit()
    return cur.rowcount > 0


def clear_chat_sessions() -> int:
    """清空所有问答历史，返回删除条数"""
    conn = get_db()
    cur = conn.execute('DELETE FROM chat_sessions')
    conn.commit()
    return cur.rowcount