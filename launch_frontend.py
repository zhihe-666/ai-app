#!/usr/bin/env python3
"""启动前端 Vite dev server"""
import subprocess, sys, os, time

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend'))
log = open('/tmp/vite.log', 'w')
p = subprocess.Popen(
    ['npx', 'vite', '--port', '5173'],
    stdout=log, stderr=subprocess.STDOUT,
    cwd=os.getcwd(),
    start_new_session=True,
)
print(f"Vite started, PID={p.pid}")
time.sleep(3)
if p.poll() is None:
    print("Process is running")
else:
    print(f"Process exited with code {p.returncode}")
