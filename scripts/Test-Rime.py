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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dll', required=True)
    parser.add_argument('--shared', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    user = root / '.verification' / ('rime-' + uuid.uuid4().hex)
    user.mkdir(parents=True)
    shutil.copy2(root / 'rime/bihua_mvp.schema.yaml', user)
    dictionary = (root / 'vendor/rime-stroke/stroke.dict.yaml').read_text(encoding='utf-8')
    (user / 'bihua_mvp.dict.yaml').write_text(
        dictionary.replace('\nname: stroke\n', '\nname: bihua_mvp\n', 1), encoding='utf-8')
    (user / 'default.custom.yaml').write_text(
        'patch:\n  schema_list:\n    - schema: bihua_mvp\n', encoding='utf-8')
    dll = c.CDLL(str(Path(args.dll).resolve()))
    session_type = c.c_size_t

    def bind(name, restype, *argtypes):
        fn = getattr(dll, name)
        fn.restype, fn.argtypes = restype, list(argtypes)
        return fn

    setup = bind('RimeSetup', None, c.POINTER(Traits))
    initialize = bind('RimeInitialize', None, c.POINTER(Traits))
    finalize = bind('RimeFinalize', None)
    maintenance = bind('RimeStartMaintenance', c.c_int, c.c_int)
    join = bind('RimeJoinMaintenanceThread', None)
    create = bind('RimeCreateSession', session_type)
    destroy = bind('RimeDestroySession', c.c_int, session_type)
    select = bind('RimeSelectSchema', c.c_int, session_type, c.c_char_p)
    process = bind('RimeProcessKey', c.c_int, session_type, c.c_int, c.c_int)
    get_context = bind('RimeGetContext', c.c_int, session_type, c.POINTER(Context))
    free_context = bind('RimeFreeContext', c.c_int, c.POINTER(Context))
    get_commit = bind('RimeGetCommit', c.c_int, session_type, c.POINTER(Commit))
    free_commit = bind('RimeFreeCommit', c.c_int, c.POINTER(Commit))
    clear = bind('RimeClearComposition', None, session_type)
    set_option = bind('RimeSetOption', None, session_type, c.c_char_p, c.c_int)
    traits = initialized(Traits)
    traits.shared_data_dir = str(Path(args.shared).resolve()).encode('utf-8')
    traits.user_data_dir = str(user).encode('utf-8')
    traits.app_name = b'rime.bihua_mvp_test'
    traits.log_dir = b''  # Glog cannot reliably open non-ASCII Windows log paths.
    traits.min_log_level = 2
    setup(c.byref(traits))
    initialize(c.byref(traits))
    results = {}
    session = 0
    try:
        maintenance(1)
        join()
        assert (user / 'build/bihua_mvp.schema.yaml').is_file(), 'Schema compilation failed'
        assert (user / 'build/bihua_mvp.table.bin').is_file(), 'Dictionary compilation failed'
        results['compilation'] = 'PASS'
        session = create()
        assert session and select(session, b'bihua_mvp'), 'Cannot select MVP schema'
        set_option(session, b'ascii_mode', 0)

        def key(code):
            return bool(process(session, ord(code) if isinstance(code, str) else code, 0))

        def snapshot():
            ctx = initialized(Context)
            assert get_context(session, c.byref(ctx)), 'Cannot read engine context'
            try:
                return {
                    'preedit': text(ctx.composition.preedit), 'page': ctx.menu.page_no,
                    'candidates': [text(ctx.menu.candidates[i].text)
                                   for i in range(ctx.menu.num_candidates)]}
            finally:
                free_context(c.byref(ctx))

        def commit():
            out = initialized(Commit)
            if not get_commit(session, c.byref(out)):
                return ''
            try:
                return text(out.text)
            finally:
                free_commit(c.byref(out))

        for char, code in [('天', 'hhpn'), ('木', 'hspn'), ('中', 'szhs'), ('国', 'szhhshdh')]:
            clear(session)
            for stroke in code:
                assert key(stroke), f'Unconsumed stroke: {stroke}'
            ctx = snapshot()
            assert char in ctx['candidates'], f'{char} missing from first page: {ctx}'
            key(str(ctx['candidates'].index(char) + 1))
            assert commit() == char, f'Wrong commit for {char}'
            results[char] = 'PASS'

        clear(session)
        key('h')
        assert snapshot()['candidates'], 'No prefix candidates'
        first_page = snapshot()
        key('=')
        assert snapshot()['page'] == 1, 'Next page failed'
        key('-')
        assert snapshot()['page'] == 0, 'Previous page failed'
        key(' ')
        assert commit() == first_page['candidates'][0], 'Space selection failed'
        results['prefix_paging_space'] = 'PASS'

        for stroke in 'hhpn':
            key(stroke)
        key(0xFF08)  # BackSpace
        assert snapshot()['preedit'] == '一一丿', 'Backspace failed'
        key(0xFF1B)  # Escape
        assert snapshot()['preedit'] == '' and commit() == '', 'Escape failed'
        results['backspace_escape'] = 'PASS'

        for num in (1, 1, 3, 4):
            key(0xFFB0 + num)  # X11 KP_1 ... KP_5, as used by Rime
        ctx = snapshot()
        assert ctx['preedit'] == '一一丿丶' and '天' in ctx['candidates'], ctx
        key(str(ctx['candidates'].index('天') + 1))
        assert commit() == '天', 'Keypad selection failed'
        results['keypad'] = 'PASS'

        clear(session)
        set_option(session, b'ascii_mode', 1)
        consumed = key(0xFFB1)
        results['ascii_keypad'] = {'consumed': consumed, 'commit': commit(), 'context': snapshot()}
        assert not consumed and not results['ascii_keypad']['commit'], 'ASCII keypad unexpectedly intercepted'
        assert not key('d') and commit() == '', 'ASCII D unexpectedly intercepted'

        set_option(session, b'ascii_mode', 0)
        clear(session)
        # A non-stroke letter must not start the pinyin translator. Existing
        # composition is cleared first: express_editor legitimately commits it
        # when a non-alphabet key is typed, which is a separate editor behavior.
        assert not key('a'), 'Non-stroke letter consumed by the scheme'
        assert not snapshot()['candidates'] and commit() == '', 'Pinyin candidates unexpectedly generated'
        key('`')
        assert not snapshot()['candidates'], 'Pinyin prefix unexpectedly enabled'
        commit()  # Default punctuation may commit a literal backtick.
        results['no_pinyin'] = 'PASS'

        for expected, code, traditional in [
            ('国', 'szhszhhzpnh', '國'),
            ('汉', 'nnhhsshszhhhpn', '漢'),
            ('龙', 'nhnphszhhhzhzhhh', '龍'),
        ]:
            clear(session)
            for stroke in code:
                key(stroke)
            ctx = snapshot()
            assert expected in ctx['candidates'] and traditional not in ctx['candidates'], ctx
            assert len(ctx['candidates']) == len(set(ctx['candidates'])), 'Duplicate simplified candidates'
            key(str(ctx['candidates'].index(expected) + 1))
            assert commit() == expected, f'Simplified commit failed: {expected}'
        results['simplified_output'] = 'PASS'
    finally:
        if session:
            destroy(session)
        finalize()
        results['dll'] = str(Path(args.dll).resolve())
        results['shared'] = str(Path(args.shared).resolve())
        results['sandbox'] = str(user)
        (user / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
