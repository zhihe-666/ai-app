"""
deep_gates.py — 深度模式人工闸口管理

3 个人工闸口：
  - conflict（Agent1 之后）：冲突确认
  - impact（Agent2 之后）：影响范围确认
  - spec（Agent3 之后）：功能规格确认

机制：
  - SSE generator 在 gate 处 yield gate 事件后 wait(threading.Event)
  - POST /api/prd/sessions/<id>/deep/approve 唤醒，set Event + 存用户响应
  - generator 继续，取用户响应决定走向

每个会话独立 gate 状态，存全局 dict {session_id: {gate_name: GateState}}。
会话完成/出错时清理。
"""
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

# 全局闸口状态：{session_id: {gate_name: GateState}}
_gates: dict[str, dict[str, 'GateState']] = {}
_gates_lock = threading.Lock()


class GateState:
    """单闸口状态"""

    def __init__(self, name: str):
        self.name = name
        self.event = threading.Event()
        self.approved = False
        self.modifications = ''
        self.waiting = False  # 是否正在等待（用于校验闸口是否活跃）

    def wait(self, timeout: float = 1800) -> bool:
        """等待用户审批，默认 30 分钟超时"""
        self.waiting = True
        try:
            return self.event.wait(timeout=timeout)
        finally:
            self.waiting = False

    def release(self, approved: bool, modifications: str = ''):
        """用户审批后唤醒"""
        self.approved = approved
        self.modifications = modifications
        self.event.set()


def _get_session_gates(session_id: str) -> dict[str, GateState]:
    """获取会话的闸口 dict（不存在则建）"""
    with _gates_lock:
        if session_id not in _gates:
            _gates[session_id] = {}
        return _gates[session_id]


def get_or_create_gate(session_id: str, gate_name: str) -> GateState:
    """获取或创建闸口"""
    session_gates = _get_session_gates(session_id)
    with _gates_lock:
        if gate_name not in session_gates:
            session_gates[gate_name] = GateState(gate_name)
        return session_gates[gate_name]


def approve_gate(session_id: str, gate_name: str, approved: bool, modifications: str = '') -> bool:
    """用户审批闸口（由 POST /deep/approve 调用）

    Returns:
        True=闸口存在且已唤醒，False=闸口不存在或未在等待
    """
    with _gates_lock:
        session_gates = _gates.get(session_id)
        if not session_gates or gate_name not in session_gates:
            return False
        gate = session_gates[gate_name]
        if not gate.waiting:
            # 闸口未在等待，可能是已审批或未到该 gate
            logger.warning(f'[DeepGate] 闸口 {session_id}/{gate_name} 未在等待')
            return False
        gate.release(approved, modifications)
        logger.info(f'[DeepGate] 闸口 {session_id}/{gate_name} 审批: approved={approved}')
        return True


def cleanup_session(session_id: str):
    """清理会话所有闸口状态"""
    with _gates_lock:
        if session_id in _gates:
            for gate in _gates[session_id].values():
                gate.event.set()  # 唤醒所有等待中的
            del _gates[session_id]
            logger.info(f'[DeepGate] 清理会话 {session_id} 闸口')


def get_gate_response(session_id: str, gate_name: str) -> dict | None:
    """获取闸口用户响应（approved + modifications）"""
    with _gates_lock:
        session_gates = _gates.get(session_id)
        if not session_gates or gate_name not in session_gates:
            return None
        gate = session_gates[gate_name]
        if not gate.event.is_set():
            return None
        return {'approved': gate.approved, 'modifications': gate.modifications}
