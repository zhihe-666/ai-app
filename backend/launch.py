#!/usr/bin/env python3
"""以独立进程方式启动 Flask 后端"""
import subprocess, sys, os, time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
log = open('/tmp/flask_backend.log', 'w')
p = subprocess.Popen(
    [sys.executable, 'run.py'],
    stdout=log, stderr=subprocess.STDOUT,
    cwd=os.getcwd(),
    start_new_session=True,  # 独立进程组，不被父进程退出影响
)
print(f"Flask backend started, PID={p.pid}")
print(f"Waiting 3s for startup...")
time.sleep(3)
# 检查进程是否存活
if p.poll() is None:
    print("Process is running")
else:
    print(f"Process exited with code {p.returncode}")
