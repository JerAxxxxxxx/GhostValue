"""Local save backups and narrowly scoped Windows memory access."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import struct
import zipfile

from .paths import DATA_DIR

ROOT = DATA_DIR
SAVE_DIR = Path(os.environ.get('APPDATA', '')) / 'kingdom_rush_genesis'
TARGET = 'Kingdom Rush Genesis.exe'
BUDGETS = {
    'tower': [0, 2, 4, 6, 8, 10, 13, 18, 21, 24, 27, 30, 35, 38, 41, 46, 51, 56],
    'hero': [0, 4, 8, 12, 16, 20, 24, 28, 32, 36],
}


class MemoryValueChanged(RuntimeError):
    """Pre-write value changed; no write took place."""


class MemoryReadbackChanged(RuntimeError):
    """WriteProcessMemory succeeded, but the game changed the readback value."""


def backup_save(source=SAVE_DIR, destination=ROOT / 'backups'):
    source, destination = Path(source), Path(destination)
    files = sorted(p for p in source.iterdir() if p.is_file())
    if not files:
        raise ValueError('没有找到存档文件')
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.zip')
    data = {p.name: p.read_bytes() for p in files}
    hashes = {n: hashlib.sha256(b).hexdigest() for n, b in data.items()}
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, b in data.items():
            z.writestr(n, b)
        z.writestr('_ghostvalue_manifest.json', json.dumps(hashes))
    with zipfile.ZipFile(path) as z:
        for n, expected in hashes.items():
            if hashlib.sha256(z.read(n)).hexdigest() != expected:
                raise IOError('备份校验失败')
    return path


class PROCESSENTRY32W(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ProcessID', W.DWORD),
                ('th32DefaultHeapID', C.c_size_t), ('th32ModuleID', W.DWORD),
                ('cntThreads', W.DWORD), ('th32ParentProcessID', W.DWORD),
                ('pcPriClassBase', W.LONG), ('dwFlags', W.DWORD), ('szExeFile', W.WCHAR * 260)]


class MEMORY_BASIC_INFORMATION(C.Structure):
    _fields_ = [('BaseAddress', C.c_void_p), ('AllocationBase', C.c_void_p),
                ('AllocationProtect', W.DWORD), ('PartitionId', W.WORD),
                ('RegionSize', C.c_size_t), ('State', W.DWORD),
                ('Protect', W.DWORD), ('Type', W.DWORD)]


kernel = C.WinDLL('kernel32', use_last_error=True)
for name, args, result in [
    ('CreateToolhelp32Snapshot', [W.DWORD, W.DWORD], W.HANDLE),
    ('Process32FirstW', [W.HANDLE, C.POINTER(PROCESSENTRY32W)], W.BOOL),
    ('Process32NextW', [W.HANDLE, C.POINTER(PROCESSENTRY32W)], W.BOOL),
    ('OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
    ('CloseHandle', [W.HANDLE], W.BOOL),
    ('VirtualQueryEx', [W.HANDLE, C.c_void_p, C.POINTER(MEMORY_BASIC_INFORMATION), C.c_size_t], C.c_size_t),
    ('ReadProcessMemory', [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)], W.BOOL),
    ('WriteProcessMemory', [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)], W.BOOL),
    ('GetExitCodeProcess', [W.HANDLE, C.POINTER(W.DWORD)], W.BOOL),
]:
    fn = getattr(kernel, name)
    fn.argtypes, fn.restype = args, result


def game_pids():
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    entry = PROCESSENTRY32W()
    entry.dwSize = C.sizeof(entry)
    found = []
    try:
        ok = kernel.Process32FirstW(handle, C.byref(entry))
        while ok:
            if entry.szExeFile.lower() == TARGET.lower():
                found.append(entry.th32ProcessID)
            ok = kernel.Process32NextW(handle, C.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    return found


def encode_value(value, kind):
    value = int(value)
    if kind not in ('double', 'int32'):
        raise ValueError('不支持的数值类型')
    if not 0 <= value <= 10_000_000:
        raise ValueError('请输入 0 到 10000000 之间的整数')
    return struct.pack('<d' if kind == 'double' else '<i', value)


class Memory:
    def __init__(self, pid):
        self.pid = pid
        self.handle = kernel.OpenProcess(0x410, False, pid)  # query + read only
        if not self.handle:
            raise C.WinError(C.get_last_error())

    def close(self):
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None

    def alive(self):
        code = W.DWORD()
        return bool(self.handle and kernel.GetExitCodeProcess(self.handle, C.byref(code)) and code.value == 259)

    def read(self, address, size):
        buffer = C.create_string_buffer(size)
        got = C.c_size_t()
        kernel.ReadProcessMemory(self.handle, address, buffer, size, C.byref(got))
        return buffer.raw[:got.value]

    def scan(self, value, kind, candidates=None):
        needle = encode_value(value, kind)
        if not self.alive():
            raise RuntimeError('游戏已经退出，请重新连接')
        if candidates is not None:
            return [a for a in candidates if self.read(a, len(needle)) == needle]
        return self.scan_bytes(needle)

    def scan_bytes(self, needle):
        if not needle or not self.alive():
            raise RuntimeError('搜索内容为空或游戏已经退出')
        result, address = [], 0
        info = MEMORY_BASIC_INFORMATION()
        while kernel.VirtualQueryEx(self.handle, address, C.byref(info), C.sizeof(info)):
            base, size = info.BaseAddress or 0, info.RegionSize
            if not size or base + size <= address:
                break
            if info.State == 0x1000 and not info.Protect & 0x100 and info.Protect & 0xFF in (4, 8, 0x40, 0x80):
                for offset in range(0, size, 1024 * 1024):
                    block = self.read(base + offset, min(1024 * 1024 + len(needle) - 1, size - offset))
                    pos = block.find(needle)
                    while pos >= 0:
                        if pos < 1024 * 1024 and (base + offset + pos) % 4 == 0:
                            result.append(base + offset + pos)
                            if len(result) > 100_000:
                                raise ValueError('候选过多，请让金币变为更特殊的数值后重新扫描')
                        pos = block.find(needle, pos + 1)
            address = base + size
        return result

    def write_verified(self, address, old_value, new_value, kind):
        old, new = encode_value(old_value, kind), encode_value(new_value, kind)
        self.write_block_verified(address, old, new)

    def write_block_verified(self, address, old, new):
        if not old or len(old) != len(new):
            raise ValueError('新旧数据长度必须一致且非空')
        if not self.alive():
            raise RuntimeError('游戏已经退出，请重新连接')
        if self.read(address, len(old)) != old:
            raise MemoryValueChanged('数值已变化或地址失效，请重新定位')
        handle = kernel.OpenProcess(0x28, False, self.pid)  # write access only for this action
        if not handle:
            raise C.WinError(C.get_last_error())
        try:
            written = C.c_size_t()
            buffer = C.create_string_buffer(new)
            if not kernel.WriteProcessMemory(handle, address, buffer, len(new), C.byref(written)) or written.value != len(new):
                raise C.WinError(C.get_last_error())
        finally:
            kernel.CloseHandle(handle)
        if self.read(address, len(new)) != new:
            raise MemoryReadbackChanged('写入已完成，但读回值已变化，请检查游戏状态')


def pack_budget(values):
    return struct.pack('<' + 'd' * len(values), *values)


def locate_budget(memory, kind):
    """Recognize the complete table, including a previously verified session edit."""
    values = BUDGETS[kind][:]
    session_file = ROOT / 'logs' / 'upgrade_candidates.json'
    if session_file.exists():
        try:
            state = json.loads(session_file.read_text())
            entry = state['tables'][kind]
            if state['pid'] == memory.pid and len(entry['values']) == len(values):
                recorded = entry['values']
                if all(isinstance(v, (int, float)) and 0 <= v <= 1_000_000 for v in recorded):
                    pattern = pack_budget(recorded)
                    for address in entry['addresses']:
                        if memory.read(address, len(pattern)) == pattern:
                            return address, recorded
        except (ValueError, KeyError, TypeError, OSError):
            pass
    matches = memory.scan_bytes(pack_budget(values))
    if len(matches) != 1:
        raise RuntimeError(f'升级配置匹配到 {len(matches)} 处，无法可靠定位；请重新启动游戏后再试')
    return matches[0], values


def add_budget(memory, kind, amount):
    if kind not in BUDGETS or not isinstance(amount, int) or not 1 <= amount <= 100:
        raise ValueError('每次增加额度须为 1 到 100 的整数')
    address, previous = locate_budget(memory, kind)
    updated = [v + amount for v in previous]
    if max(updated) > 1_000_000:
        raise ValueError('额度超过原型支持范围')
    backup = backup_save()
    log_action('budget_write_attempt', kind=kind, previous=previous, updated=updated, backup=str(backup))
    memory.write_block_verified(address, pack_budget(previous), pack_budget(updated))
    session_file = ROOT / 'logs' / 'upgrade_candidates.json'
    state = {'pid': memory.pid, 'tables': {}}
    if session_file.exists():
        try:
            old = json.loads(session_file.read_text())
            if old.get('pid') == memory.pid:
                state = old
        except (ValueError, OSError):
            pass
    state['tables'][kind] = {'values': updated, 'addresses': [address]}
    session_file.write_text(json.dumps(state))
    log_action('budget_write_readback_verified', kind=kind, amount=amount)
    return backup


def log_action(action, **details):
    folder = ROOT / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'actions.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps({'time': datetime.now().isoformat(), 'action': action, **details}, ensure_ascii=False) + '\n')
