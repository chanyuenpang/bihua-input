"""Shared validation and Windows lock protocol for offline personal-data tools."""
from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import uuid


def checksum(data):
    value = 2166136261
    for byte in data.encode('utf-8'):
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return f'{value:08x}'


def lock_name(path):
    # Match Lua string.lower(): ASCII only, not Unicode case folding.
    normalized = path.name.translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))
    return 'bihua_association_lock_' + checksum(normalized) + '.userdb'


@contextmanager
def association_lock(path):
    if os.name != 'nt':
        raise RuntimeError('This management tool currently requires Windows')
    directory = path.parent / lock_name(path)
    directory.mkdir(parents=True, exist_ok=True)
    api = c.WinDLL('kernel32', use_last_error=True)
    create = api.CreateFileW
    create.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    create.restype = w.HANDLE
    close = api.CloseHandle
    close.argtypes, close.restype = [w.HANDLE], w.BOOL
    handle = create(str(directory / 'LOCK'), 0xC0000000, 1, None, 4, 0x80, None)
    if handle == c.c_void_p(-1).value:
        raise RuntimeError('个人联想正在使用中，或锁不可用；请退出小狼毫后重试。原数据未修改。')
    try:
        # Holding a write handle with FILE_SHARE_READ already excludes LevelDB's
        # write-open and other managers. Also take the matching OS byte-range lock.
        lock = api.LockFile
        lock.argtypes, lock.restype = [w.HANDLE, w.DWORD, w.DWORD, w.DWORD, w.DWORD], w.BOOL
        if not lock(handle, 0, 0, 0xffffffff, 0xffffffff):
            raise RuntimeError('个人联想数据库锁被占用，原数据未修改。')
        yield
    finally:
        close(handle)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    try:
        with temporary.open('x', encoding='utf-8', newline='\n') as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_snapshot(path):
    envelope = json.loads(path.read_text(encoding='utf-8'))
    if envelope['format'] != 1 or checksum(envelope['payload']) != envelope['checksum']:
        raise ValueError('Personal snapshot checksum/format mismatch')
    if not isinstance(envelope['revision'], int) or envelope['revision'] < 1:
        raise ValueError('Invalid personal snapshot revision')
    state = json.loads(envelope['payload'])
    validate_snapshot(state)
    return envelope, state


def han(text):
    return bool(text) and all(0x3400 <= ord(char) <= 0x9fff or 0xf900 <= ord(char) <= 0xfaff or
                              0x20000 <= ord(char) <= 0x323af for char in text)


def validate_snapshot(state):
    import math
    def require(condition):
        if not condition:
            raise ValueError('Invalid personal association state')
    require(state['version'] in (1, 2) and isinstance(state['capacity'], int) and 1 <= state['capacity'] <= 5000)
    if state['version'] == 1:
        require(0 < state['half_life'] < math.inf and 0 < state['minimum_weight'] <= state['maximum_strength'] < math.inf)
    else:
        require(state['policy'] == 'shown_choice_v1')
    require(isinstance(state['sequence'], int) and state['sequence'] >= 0 and isinstance(state['segment'], int) and state['segment'] >= 1)
    require(len(state['window']) <= state['capacity'])
    previous = 0
    for event in state['window']:
        require(han(event['text']) and len(event['text']) == 1)
        require(isinstance(event['sequence'], int) and previous < event['sequence'] <= state['sequence'])
        require(isinstance(event['segment'], int) and 1 <= event['segment'] <= state['segment'])
        require(0 <= event['observed_at'] < math.inf)
        previous = event['sequence']
    if state['confirmed'] == []:
        state['confirmed'] = {}
    for phrase, record in state['confirmed'].items():
        require(han(phrase) and 2 <= len(phrase) <= 8)
        if state['version'] == 1:
            require(isinstance(record['count'], int) and record['count'] >= 1)
            require(0 <= record['strength'] <= state['maximum_strength'])
            require(0 <= record['last_used_at'] < math.inf)
        else:
            require(type(record['score']) is int and 0 <= record['score'] <= 20)
            require(type(record['positive_count']) is int and record['positive_count'] >= 0)
            require(type(record['negative_count']) is int and record['negative_count'] >= 0)
            require(type(record['hidden_sequence']) is int and 0 <= record['hidden_sequence'] <= state['sequence'])
            require(0 <= record['last_feedback_at'] < math.inf)
            require(record['origin'] in ('personal', 'provisional', 'static'))
        require(isinstance(record['recent'], int) and 0 <= record['recent'] <= state['sequence'])
