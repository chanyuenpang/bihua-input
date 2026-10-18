"""Exercise the real Rime DLL in a private user directory, without UI input.

Python 3, standard library only. ABI definitions follow the Rime public headers.
This verifies engine behavior, not Windows TSF integration or application input.
"""
import argparse
import ctypes as c
import json
from pathlib import Path
import shutil
import uuid


class Traits(c.Structure):
    _fields_ = [('data_size', c.c_int)] + [
        (name, c.c_char_p) for name in (
            'shared_data_dir', 'user_data_dir', 'distribution_name',
            'distribution_code_name', 'distribution_version', 'app_name')
    ] + [('modules', c.POINTER(c.c_char_p)), ('min_log_level', c.c_int)] + [
        (name, c.c_char_p) for name in ('log_dir', 'prebuilt_data_dir', 'staging_dir')
    ]


class Composition(c.Structure):
    _fields_ = [(name, c.c_int) for name in
                ('length', 'cursor_pos', 'sel_start', 'sel_end')] + [('preedit', c.c_char_p)]


class Candidate(c.Structure):
    _fields_ = [('text', c.c_char_p), ('comment', c.c_char_p), ('reserved', c.c_void_p)]


class Menu(c.Structure):
    _fields_ = [(name, c.c_int) for name in (
        'page_size', 'page_no', 'is_last_page', 'highlighted_candidate_index', 'num_candidates')
    ] + [('candidates', c.POINTER(Candidate)), ('select_keys', c.c_char_p)]


class Context(c.Structure):
    _fields_ = [('data_size', c.c_int), ('composition', Composition), ('menu', Menu),
                ('commit_text_preview', c.c_char_p), ('select_labels', c.POINTER(c.c_char_p))]


class Commit(c.Structure):
    _fields_ = [('data_size', c.c_int), ('text', c.c_char_p)]


def initialized(cls):
    obj = cls()
    obj.data_size = c.sizeof(cls) - c.sizeof(c.c_int)
    return obj


def text(value):
    return value.decode('utf-8') if value else ''

