"""Test the local mobile-data experiment against real Rime, without UI input."""
import argparse
import faulthandler
import csv
import ctypes as c
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import time
import uuid
import yaml
from key_bindings import ACTIONS, LETTER, KEYPAD

spec = importlib.util.spec_from_file_location('rime_abi', Path(__file__).with_name('Test-Rime.py'))
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)


def main():
    faulthandler.dump_traceback_later(30, repeat=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dll', required=True)
    parser.add_argument('--shared', required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--user-dir', type=Path)
    parser.add_argument('--reuse', action='store_true')
    parser.add_argument('--association-core', action='store_true')
    parser.add_argument('--association-runtime', action='store_true')
    parser.add_argument('--expected-associations', type=int, default=0)
    parser.add_argument('--static-association', action='store_true')
    parser.add_argument('--phrase-query', action='store_true')
    parser.add_argument('--phone-phrases', action='store_true')
    parser.add_argument('--expected-phrase-usage', type=int, default=0)
    parser.add_argument('--feedback-probe', action='store_true')
    parser.add_argument('--focus-helper', type=Path)
    parser.add_argument('--key-style', choices=['standard','alternative','custom'])
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    user = args.user_dir.resolve() if args.user_dir else root / '.verification' / ('local-rime-' + uuid.uuid4().hex)
    if not user.is_relative_to((root / '.verification').resolve()):
        raise ValueError('Test user directory must be private')
    if args.reuse and not (user / 'bihua_local.schema.yaml').is_file():
        raise ValueError('Reuse requires an existing prepared test directory')
    (user / 'lua').mkdir(parents=True, exist_ok=args.reuse)
    schema = (root / 'rime/bihua_local.schema.yaml').read_text(encoding='utf-8')
    schema = schema.replace('bihua_matcher:\n', 'bihua_matcher:\n  fuzzy_enabled: true\n')
    if args.key_style:
        letters = LETTER['asdfgt' if args.key_style=='alternative' else 'standard'].copy()
        keypad = KEYPAD['789456' if args.key_style=='alternative' else 'standard'].copy()
        if args.key_style=='custom':
            letters = dict(zip(ACTIONS, 'qweryui'))
            keypad = dict(zip(ACTIONS, ['KP_9','KP_8','KP_7','KP_6','KP_5','KP_4','KP_Divide']))
        schema += '\n'+yaml.safe_dump({'bihua_keys':{'letter_style':'standard' if args.key_style=='standard' else 'custom', 'letter':letters,'keypad':keypad}},sort_keys=False)
    if args.association_runtime:
        schema = schema.replace('  personal_association: false', '  personal_association: true')
        if not args.reuse:
            for name in ('bihua_association_core.lua', 'bihua_association_runtime.lua', 'bihua_association_store.lua', 'bihua_feedback_episode.lua', 'bihua_json.lua'):
                shutil.copy2(root / 'rime/lua' / name, user / 'lua')
        if args.static_association:
            schema = schema.replace('  static_association: false', '  static_association: true')
            if not args.reuse:
                shutil.copy2(args.profile / 'bihua_local_associations.lua', user / 'lua')
    if args.phrase_query:
        schema = schema.replace('processors: [ ', 'processors: [ "lua_processor@*bihua_query_keys", ')
        schema = schema.replace('segmentors: [ ', 'segmentors: [ "lua_segmentor@*bihua_query_segmentor", ')
        schema = schema.replace('  phrase_enabled: false', '  phrase_enabled: true')
        if args.phone_phrases:
            schema = schema.replace('  phrase_enabled: true', '  phrase_enabled: true\n  mobile_phrases: true')
        schema += '\nbihua_phrase:\n  dictionary: bihua_local\n  user_dict: bihua_mvp_phrase_v1\n'
        if not args.reuse:
            for name in ('bihua_phrase_query.lua', 'bihua_phrase_runtime.lua', 'bihua_phone_phrases.lua', 'bihua_query_keys.lua', 'bihua_query_segmentor.lua'):
                shutil.copy2(root / 'rime/lua' / name, user / 'lua')
            if args.phone_phrases:
                shutil.copy2(root / 'rime/lua/bihua_phone_phrases.lua', user / 'lua')
                shutil.copy2(args.profile / 'bihua_local_phrase_data.lua', user / 'lua')
            raw = {}
            with (root / '.verification/wetype-mobile/reproducible-export/wechat-mobile-strokes.tsv').open(encoding='utf-8') as file:
                for row in csv.DictReader(file, delimiter='\t'):
                    raw[row['character']] = row['stroke_digits'].translate(str.maketrans('12345', 'hspnz'))
            words = '中国 中文 中国人 中国人民 人民 人民币 人民法院 电脑 计算机 输入 输入法 笔画 文字 手机 电话 号码 用户 词库 个人 星河 星河计划 工作 学习 时间 今天 明天 朋友 家人 北京 上海'.split()
            (user / 'bihua_personal_phrases.tsv').write_text(''.join(word + '\t' + '|'.join(raw[char] for char in word) + '\t' + ('1e+09' if word == '中国' else '1e-05' if word == '上海' else '1') + '\n' for word in words), encoding='utf-8')
        if args.phone_phrases and not args.reuse and not args.association_core:
            schema = schema.replace('lua_translator@*bihua_matcher', 'lua_translator@*bihua_phone_probe')
            (user / 'lua/bihua_phone_probe.lua').write_text('''
local matcher = require("bihua_matcher")
return {init=function(env)
  matcher.init(env)
  local reports = {}
  for _, input in ipairs({"s|s", "sz|sz", "szh|szh", "szh|s?h"}) do
    local start = os.clock()
    local rows, diagnostic = require("bihua_phone_phrases").query(input, env.data, env.phone_phrase_data)
    local rank
    for i, row in ipairs(rows) do if row.text == "中国" then rank = i end end
    assert(rank, "mobile-only China missing: " .. input)
    assert(diagnostic.lookups <= 120 and diagnostic.scanned <= 20000 and #rows <= 120)
    reports[#reports+1] = {input=input, china_rank=rank, scanned=diagnostic.scanned,
      lookups=diagnostic.lookups, ms=(os.clock()-start)*1000, first=rows[1].text}
  end
  env.engine.context:set_property("bihua_phone_probe", require("bihua_json").encode(reports))
end, func=matcher.func, fini=matcher.fini}
''', encoding='utf-8')
    if args.association_core:
        if args.reuse:
            raise ValueError('Association core probe requires a fresh directory')
        schema = schema.replace('lua_translator@*bihua_matcher', 'lua_translator@*bihua_test_runner')
        shutil.copy2(root / 'rime/lua/bihua_association_core.lua', user / 'lua')
        shutil.copy2(root / 'tests/lua/association_spec.lua', user / 'lua')
        shutil.copy2(root / 'tests/lua/association_store_spec.lua', user / 'lua')
        for name in ('bihua_association_store.lua', 'bihua_feedback_episode.lua', 'bihua_json.lua'):
            shutil.copy2(root / 'rime/lua' / name, user / 'lua')
        shutil.copy2(root / 'rime/lua/bihua_phrase_query.lua', user / 'lua')
        shutil.copy2(root / 'tests/lua/phrase_query_spec.lua', user / 'lua')
        shutil.copy2(root / 'tests/lua/packed_data_spec.lua', user / 'lua')
        if args.phrase_query:
            shutil.copy2(root / 'tests/lua/phrase_runtime_spec.lua', user / 'lua')
            shutil.copy2(root / 'tests/lua/personal_stroke_weight_spec.lua', user / 'lua')
        (user / 'lua/bihua_test_runner.lua').write_text(
            'local matcher = require("bihua_matcher")\n'
            'return {init=function(env) matcher.init(env); '
            'env.engine.context:set_property("bihua_association_core_test", "RUNNING"); '
            'env.engine.context:set_property("bihua_association_store_test", "RUNNING"); '
            'env.engine.context:set_property("bihua_association_core_test", require("association_spec").run()) '
            '; assert(require("phrase_query_spec").run():sub(1, 4) == "PASS") '
            '; assert(require("packed_data_spec").run():sub(1, 4) == "PASS") '
            + ('; assert(require("phrase_runtime_spec").run():sub(1, 4) == "PASS"); assert(require("personal_stroke_weight_spec").run():sub(1, 4) == "PASS") ' if args.phrase_query else '') +
            '; env.engine.context:set_property("bihua_association_store_test", require("association_store_spec").run(rime_api.get_user_data_dir())) '
            'end, func=matcher.func, fini=matcher.fini}\n', encoding='utf-8')
    if not args.reuse:
        (user / 'bihua_local.schema.yaml').write_text(schema, encoding='utf-8')
        shutil.copy2(args.profile / 'bihua_local.dict.yaml', user)
        shutil.copy2(args.profile / 'bihua_local.manifest.json', user)
        shutil.copy2(args.profile / 'bihua_local_data.lua', user / 'lua')
        for name in ('bihua_matcher.lua', 'bihua_character_learning.lua', 'bihua_learning_guard.lua', 'bihua_packed_data.lua', 'bihua_association_filter.lua', 'bihua_personal_stroke_runtime.lua'):
            shutil.copy2(root / 'rime/lua' / name, user / 'lua')
        (user / 'default.custom.yaml').write_text('patch:\n  schema_list:\n    - schema: bihua_local\n', encoding='utf-8')
    expected = {}
    with (root / '.verification/wetype-mobile/reproducible-export/wechat-mobile-stroke-candidates.tsv').open(encoding='utf-8') as file:
        for row in csv.DictReader(file, delimiter='\t'):
            expected.setdefault(row['stroke_prefix'], []).append(row['candidate'])
    dll = c.CDLL(str(Path(args.dll).resolve()))

    def bind(name, restype, *types):
        fn = getattr(dll, name)
        fn.restype, fn.argtypes = restype, list(types)
        return fn

    setup = bind('RimeSetup', None, c.POINTER(abi.Traits))
    initialize = bind('RimeInitialize', None, c.POINTER(abi.Traits))
    finalize = bind('RimeFinalize', None)
    maintenance = bind('RimeStartMaintenance', c.c_int, c.c_int)
    join = bind('RimeJoinMaintenanceThread', None)
    create = bind('RimeCreateSession', c.c_size_t)
    destroy = bind('RimeDestroySession', c.c_int, c.c_size_t)
    select = bind('RimeSelectSchema', c.c_int, c.c_size_t, c.c_char_p)
    process = bind('RimeProcessKey', c.c_int, c.c_size_t, c.c_int, c.c_int)
    context = bind('RimeGetContext', c.c_int, c.c_size_t, c.POINTER(abi.Context))
    free_context = bind('RimeFreeContext', c.c_int, c.POINTER(abi.Context))
    clear = bind('RimeClearComposition', None, c.c_size_t)
    option = bind('RimeSetOption', None, c.c_size_t, c.c_char_p, c.c_int)
    get_option = bind('RimeGetOption', c.c_int, c.c_size_t, c.c_char_p)
    commit_composition = bind('RimeCommitComposition', c.c_int, c.c_size_t)
    get_commit = bind('RimeGetCommit', c.c_int, c.c_size_t, c.POINTER(abi.Commit))
    free_commit = bind('RimeFreeCommit', c.c_int, c.POINTER(abi.Commit))
    get_property = bind('RimeGetProperty', c.c_int, c.c_size_t, c.c_char_p, c.c_char_p, c.c_size_t)
    set_property = bind('RimeSetProperty', None, c.c_size_t, c.c_char_p, c.c_char_p)
    traits = abi.initialized(abi.Traits)
    traits.shared_data_dir = str(Path(args.shared).resolve()).encode()
    traits.user_data_dir = str(user).encode()
    traits.app_name = b'rime.bihua_local_test'
    traits.log_dir = b''
    traits.min_log_level = 2
    setup(c.byref(traits))
    start = time.perf_counter()
    initialize(c.byref(traits))
    session = 0
    result = {'sandbox': str(user), 'fuzzy_removed': True, 'dll': args.dll}
    static_paths = [user / 'bihua_local.schema.yaml', user / 'bihua_local.dict.yaml',
                    user / 'bihua_local.manifest.json', user / 'lua/bihua_local_data.lua']
    static_hashes = {str(path.relative_to(user)): hashlib.sha256(path.read_bytes()).hexdigest() for path in static_paths}
    try:
        if not args.reuse:
            maintenance(1)
            join()
        session = create()
        assert session and select(session, b'bihua_local'), 'Cannot select local schema'
        result['startup_ms'] = round((time.perf_counter() - start) * 1000, 3)
        if args.phone_phrases and not args.reuse and not args.association_core:
            buffer = c.create_string_buffer(8192)
            get_property(session, b'bihua_phone_probe', buffer, len(buffer))
            result['mobile_only_recall'] = json.loads(buffer.value.decode('utf-8'))
        option(session, b'ascii_mode', 0)
        assert get_option(session, b'simplification'), 'Simplification is not on by default'

        def key(char):
            return bool(process(session, ord(char) if isinstance(char, str) else char, 0))

        def snapshot():
            ctx = abi.initialized(abi.Context)
            assert context(session, c.byref(ctx))
            try:
                return {'page': ctx.menu.page_no, 'preedit': abi.text(ctx.composition.preedit),
                        'candidates': [abi.text(ctx.menu.candidates[i].text) for i in range(ctx.menu.num_candidates)],
                        'comments': [abi.text(ctx.menu.candidates[i].comment) for i in range(ctx.menu.num_candidates)]}
            finally:
                free_context(c.byref(ctx))

        key_timings = []

        def query(code):
            clear(session)
            for char in code:
                started = time.perf_counter()
                key({'|': 0xFFB7, '?': 0xFFB6}.get(char, char) if args.phrase_query else char)
                key_timings.append((time.perf_counter() - started) * 1000)
            return snapshot()

        def property(name):
            buffer = c.create_string_buffer(2048)
            get_property(session, name.encode(), buffer, len(buffer))
            return buffer.value.decode('utf-8')

        def read_commit():
            out = abi.initialized(abi.Commit)
            if not get_commit(session, c.byref(out)):
                return ''
            try:
                return abi.text(out.text)
            finally:
                free_commit(c.byref(out))

        if args.key_style:
            names={'KP_Divide':0xffaf,'KP_Multiply':0xffaa}
            def physical(name):
                return names.get(name, 0xffb0+int(name[-1]) if name.startswith('KP_') and name[-1].isdigit() else ord(name) if len(name)==1 else 0)
            def typed(actions, mapping):
                clear(session)
                read_commit()
                for action in actions: key(physical(mapping[action]))
                return snapshot()
            for mapping in (letters,keypad):
                got=typed(['h','h','p','n'],mapping)
                assert got['candidates'][0]=='天', got
                key(0xffb0)
                assert read_commit()=='天'
                assert snapshot()['candidates'], 'Keypad zero must continue prediction like Space'
                key(0xff0d)
                assert read_commit() and not snapshot()['candidates'] and not snapshot()['preedit']
                got=typed(['s','z','separator','s','z'],mapping)
                assert '中国' in got['candidates'], got
                got=typed(['h','wildcard','p','n'],mapping)
                assert '天' in got['candidates'] and '？' in got['preedit'], got
                got=typed(['h'],mapping)
                key(0xffab); page=snapshot()
                assert page['page']==1, page
                key(0xffad); assert snapshot()['page']==0
                key(0xffab); page=snapshot()
                key(0xffae); key(0xffb2)
                assert read_commit()==page['candidates'][1], (page,snapshot())
                process(session,0xffae,1<<30)
                clear(session); read_commit()
                key(physical(keypad['h']))
                assert snapshot()['preedit']=='一' and not read_commit(), snapshot()
                key(0xffae)
                if args.focus_helper:
                    helper=c.CDLL(str(args.focus_helper.resolve()))
                    helper.ProbeFocusOut.argtypes=[c.c_void_p,c.c_size_t]
                    helper.ProbeFocusOut.restype=None
                    saved_session=property('bihua_feedback_session')
                    set_property(session,b'bihua_feedback_session',b'')
                    helper.ProbeFocusOut(bind('rime_get_api',c.c_void_p)(),session)
                    assert property('bihua_keymap_reset')=='focus_out'
                    set_property(session,b'bihua_feedback_session',saved_session.encode())
                else:
                    set_property(session,b'bihua_keymap_reset',b'focus_out')
                key(physical(keypad['h']))
                assert snapshot()['preedit']=='一一' and not read_commit(), snapshot()
                process(session,0xffae,1<<30)
                last=typed(['h'],mapping)
                for _ in range(30):
                    key(0xffab); now=snapshot()
                    if now['page']==last['page']: break
                    last=now
                if len(last['candidates'])<9:
                    key(0xffae);key(0xffb9)
                    assert not read_commit() and snapshot()==last, 'Missing candidate selected or committed text'
                    process(session,0xffae,1<<30)
            clear(session)
            process(session,ord('?'),1)
            assert read_commit()=='？'
            option(session,b'ascii_mode',1)
            assert not key(0xffae) and not key(physical(keypad['h']))
            option(session,b'ascii_mode',0)
            result['key_style']=args.key_style
            result['key_style_tests']='PASS: canonical strokes, phrase prefix, wildcard, keypad +/- paging, dot+current-page selection, release/focus reset, zero continues, Enter closes, punctuation, English'
            print(json.dumps(result,ensure_ascii=True,indent=2))
            return

        if args.phrase_query:
            for modifiers in (0, 1):
                clear(session)
                process(session, ord('?'), modifiers)
                assert read_commit() == '？', ('question punctuation', modifiers, snapshot())
                assert snapshot()['preedit'] == '', snapshot()
            result['question_is_punctuation'] = 'PASS'
            first = query('h')['candidates'][0]
            process(session, ord('?'), 1)
            assert read_commit() == first + '？', snapshot()
            assert not snapshot()['candidates'] and not snapshot()['preedit']
            clear(session)
            key('h'); key('t')
            assert '？' in snapshot()['preedit'], snapshot()
            assert not read_commit(), 'T committed punctuation instead of wildcard'
            clear(session)
            option(session, b'ascii_mode', 1)
            assert not process(session, ord('?'), 1), 'English question key was swallowed'
            option(session, b'ascii_mode', 0)
            result['question_composition_and_t_wildcard'] = 'PASS'

        if args.association_runtime:
            result['association_loaded_relations'] = int(property('bihua_loaded_relations'))
            assert result['association_loaded_relations'] >= args.expected_associations, result

        translation = str.maketrans('12345', 'hspnz')
        for original, simplified, digits in [('國', '国', '25125115341'),
                                               ('漢', '汉', '44112212511134'),
                                               ('龍', '龙', '4143125111515111')]:
            projected = query(digits.translate(translation))['candidates']
            assert simplified in projected and original not in projected and len(projected) == len(set(projected)), projected
            key(str(projected.index(simplified) + 1))
            assert read_commit() == simplified
        result['default_simplification_projection_dedup_commit'] = 'PASS'
        if args.association_core:
            result['association_core'] = property('bihua_association_core_test')
            assert result['association_core'].startswith('PASS:'), result
            result['association_store'] = property('bihua_association_store_test')
            assert result['association_store'].startswith('PASS:'), result
        option(session, b'simplification', 0)

        prefixes = ['1', '2', '3', '4', '5', '11', '12', '13', '14', '15',
                    '21', '22', '23', '24', '25', '31', '32', '33', '34', '35',
                    '41', '42', '43', '44', '45', '51', '52', '53', '54', '55',
                    '41341', '25112141', '11214', '32511354', '3121534', '1134', '1234']
        timings = []
        for prefix in prefixes:
            if prefix not in expected:
                continue
            started = time.perf_counter()
            got = query(prefix.translate(translation))['candidates']
            timings.append((time.perf_counter() - started) * 1000)
            preserved = 9
            assert got[:min(preserved, len(expected[prefix]))] == expected[prefix][:preserved], (prefix, got, expected[prefix][:preserved])
        result['direct_prefix_top9_matches'] = len(timings)
        result['query_ms'] = {'max': round(max(timings), 3), 'mean': round(sum(timings) / len(timings), 3)}
        got = query('szhhsdhh')['candidates']
        assert '国' not in got, ('adjacent 国', got)
        result['adjacent_国'] = got
        assert '国' not in query('zshhhsdh')['candidates'], 'Two adjacent swaps unexpectedly matched 国'
        query('h' * 25)
        assert not snapshot()['candidates'], 'Unmatched long input returned candidates'
        assert query('nhpnh')['candidates'] == query('dhpdh')['candidates'], 'D/N mismatch'
        clear(session)
        for keypad in [0xFFB1, 0xFFB1, 0xFFB3, 0xFFB4]:
            assert key(keypad), 'Keypad stroke not consumed'
        assert '天' in snapshot()['candidates']
        assert '你好' not in query('`nihao')['candidates'], 'Unexpected pinyin translation'
        read_commit()  # Drain literal/partial commits from the non-stroke test.
        result['keypad_and_no_pinyin'] = 'PASS'
        query('p')
        key('=')
        assert snapshot()['page'] == 1, 'Paging failed'
        key('-')
        assert snapshot()['page'] == 0
        key(0xFF08)
        assert snapshot()['preedit'] == '', 'Backspace failed'
        query('hhpd')
        key(0xFF1B)
        assert not snapshot()['candidates'], 'Escape failed'
        got = query('hhpd')['candidates']
        key(str(got.index('天') + 1))
        out = abi.initialized(abi.Commit)
        assert get_commit(session, c.byref(out))
        try:
            assert abi.text(out.text) == '天', repr(abi.text(out.text))
        finally:
            free_commit(c.byref(out))
        result['selection_editing_paging_dn'] = 'PASS'
        assert query('hhpd')['preedit'] == '一一丿丶', snapshot()
        assert query('z')['preedit'] == '𠃌', snapshot()
        result['stroke_symbol_preedit'] = 'PASS: hhpd -> 一一丿丶'
        protected = query('h')
        read_commit()
        for letter in 'abcegijklm o qruv wxy'.replace(' ', '') + 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            key(letter)
            assert snapshot() == protected and read_commit() == '', ('Unexpected letter committed/changed input', letter, snapshot())
        key(0xFF1B)
        assert not snapshot()['preedit'] and read_commit() == ''
        result['unrecognized_letters_ignored'] = 'PASS: no candidate selection, literal commit or composition change'
        unmatched = query('h' * 24)
        assert unmatched['preedit'] == '一' * 24 and not unmatched['candidates'], unmatched
        result['unmatched_input_display'] = unmatched
        read_commit()
        for confirm_key in [0x20, 0xFF0D, 0xFF8D, 0xFFB0]:
            key(confirm_key)
            assert read_commit() == '' and snapshot() == unmatched, 'Unmatched stroke code committed'
        key('h')
        assert snapshot()['preedit'] == '一' * 25 and not snapshot()['candidates'], 'Display overlay changed query scope'
        key(0xFF08)
        assert snapshot()['preedit'] == '一' * 24, 'First backspace did not delete a stroke'
        for _ in range(23):
            key(0xFF08)
        assert snapshot()['preedit'] == '一' and snapshot()['candidates'], 'Real candidates failed to recover after backspace'
        key(0xFF1B)
        for confirm_key in [0x20, 0xFF0D, 0xFFB0, 0xFF8D]:
            current = query('hhpd')['candidates']
            expected_first = current[0]
            key(confirm_key)
            actual_commit = read_commit()
            assert actual_commit == expected_first, ('Keypad confirmation failed', confirm_key, expected_first, actual_commit, snapshot())
            if args.association_runtime and confirm_key in (0xFF0D, 0xFF8D):
                assert not snapshot()['preedit'] and not snapshot()['candidates'], ('Enter did not close prediction', confirm_key, snapshot())
            key(0xFF1B)
        result['keypad_zero_enter_confirmation'] = 'PASS'
        if args.association_runtime and args.static_association:
            query('h'); key(0x20); assert read_commit()
            prediction = snapshot()['candidates']
            assert prediction, 'Space stopped showing continuous predictions'
            key(0xFF0D)
            assert read_commit() == prediction[0]
            assert not snapshot()['preedit'] and not snapshot()['candidates'], 'Enter kept prediction chain open'
            result['enter_closes_prediction_space_continues'] = 'PASS'
        pages = {}
        for label, previous, following in [('minus_equal', ord('-'), ord('=')),
                                            ('brackets', ord('['), ord(']')),
                                            ('keypad_minus_plus', 0xFFAD, 0xFFAB)]:
            query('h')
            key(following)
            assert snapshot()['page'] == 1, (label, snapshot())
            key(previous)
            assert snapshot()['page'] == 0, (label, snapshot())
            pages[label] = 'PASS'
        query('h')
        key(0xFF09)
        assert snapshot()['page'] == 1, ('Tab', snapshot())
        process(session, 0xFF09, 1)
        assert snapshot()['page'] == 0, ('Shift+Tab', snapshot())
        for _ in range(20):
            key(0xFF56)
        last_page = snapshot()['page']
        key(0xFF56)
        assert snapshot()['page'] == last_page and read_commit() in ('', '天')
        expected_selection = snapshot()['candidates'][0]
        key('1')
        assert read_commit() == expected_selection
        result['paging'] = dict(pages, shift_tab_tab='PASS', last_page=last_page,
                                end_does_not_wrap_or_commit=True, selection_after_paging='PASS')
        if args.association_runtime:
            option(session, b'simplification', 1)
            read_commit()
            if args.static_association:
                candidates = query('h')['candidates']
                key(str(candidates.index('一') + 1))
                assert read_commit() == '一'
                offered = snapshot()['candidates']
                assert '个' in offered and all(len(text) == 1 for text in offered), offered
                assert not any(snapshot()['comments']), 'Prediction retained long suffixes'
                key('=')
                assert snapshot()['page'] == 1 and snapshot()['candidates'], 'Prediction did not offer another page'
                key('-')
                assert snapshot()['page'] == 0
                manual_before = property('bihua_manual_history_size')
                key(str(offered.index('个') + 1))
                assert read_commit() == '个'
                following = snapshot()['candidates']
                assert following and all(len(text) == 1 for text in following), following
                assert property('bihua_manual_history_size') == manual_before
                key(0xFF1B)
                assert not snapshot()['candidates'], 'Escape failed to dismiss static predictions'
                result['static_association'] = {'after_一': offered, 'after_个': following,
                                                'single_character_and_exclusion': 'PASS'}
            raw_codes = {}
            with (root / '.verification/wetype-mobile/reproducible-export/wechat-mobile-strokes.tsv').open(encoding='utf-8') as file:
                for row in csv.DictReader(file, delimiter='\t'):
                    raw_codes[row['character']] = row['stroke_digits'].translate(translation)
            key(0xFF1B)
            for char in '星河计划星':
                current = query(raw_codes[char])['candidates']
                assert char in current, (char, current)
                key(str(current.index(char) + 1))
                assert read_commit() == char
            chain = []
            manual_size = property('bihua_manual_history_size')
            for char in '河计划':
                current = snapshot()['candidates']
                assert char in current and all(len(text) == 1 for text in current), (char, current)
                key(str(current.index(char) + 1))
                assert read_commit() == char
                chain.append(char)
            assert property('bihua_manual_history_size') == manual_size
            assert int(property('bihua_confirmed_relations')) >= 3
            result['association_runtime_chain'] = chain
            result['association_runtime_manual_slots_unchanged'] = True
            result['association_storage_status'] = property('bihua_personal_storage_status')
            assert result['association_storage_status'] == 'ok'
            if args.feedback_probe:
                key(0xFF1B)
                def feedback_state():
                    envelope = json.loads((user / 'bihua_personal_association_v1.jsonl').read_text(encoding='utf-8'))
                    return json.loads(envelope['payload'])
                def score(records, phrase):
                    return records['confirmed'].get(phrase, {}).get('score', 10)
                def start_prediction(char):
                    candidates = query(raw_codes[char])['candidates']
                    key(str(candidates.index(char) + 1))
                    assert read_commit() == char
                    current = snapshot()
                    assert current['candidates'] and current['page'] == 0
                    return current
                initial = start_prediction('甲')
                before = feedback_state()
                key('q')
                assert feedback_state() == before and snapshot()['candidates'] == initial['candidates']
                for code, modifiers in ((ord('h'), 1 << 30), (0xFF1B, 1 << 30), (ord('h'), 4), (ord('h'), 8)):
                    process(session, code, modifiers)
                    assert feedback_state() == before and snapshot()['candidates'] == initial['candidates'], (code, modifiers)
                key('=')
                second = snapshot()
                assert second['page'] == 1
                # Old librime-lua select_notifier fires before selected_index
                # changes. The next key captures the actual current menu first.
                key('-')
                assert int(property('bihua_feedback_visible_count')) == 18
                assert feedback_state() == before, 'Paging settled an episode early'
                key('1')
                selected_text = initial['candidates'][0]
                assert read_commit() == selected_text
                after = feedback_state()
                assert score(after, '甲' + selected_text) == min(20, score(before, '甲' + selected_text) + 1)
                visible = set(initial['candidates'] + second['candidates'])
                for char in visible - {selected_text}:
                    assert score(after, '甲' + char) == max(0, score(before, '甲' + char) - 1), char
                unseen = [row['suffix'] for row in csv.DictReader((root / '.verification/wetype-mobile/reproducible-export/wechat-mobile-continuations.tsv').open(encoding='utf-8'), delimiter='\t')
                          if row['previous_character'] == '甲' and row['suffix_length'] == '1' and row['suffix'] not in visible]
                assert unseen and all(score(after, '甲' + char) == score(before, '甲' + char) for char in unseen)
                key(0xFF1B)
                shown = start_prediction('阿')['candidates']
                before_cancel = feedback_state()
                key(0xFF1B)
                cancelled = feedback_state()
                assert all(score(cancelled, '阿' + char) == max(0, score(before_cancel, '阿' + char) - 1) for char in shown)
                key(0xFF1B)
                assert feedback_state() == cancelled, 'Repeated Escape deducted twice'
                shown = start_prediction('海')['candidates']
                before_typing = feedback_state()
                key('h')
                typed = feedback_state()
                assert all(score(typed, '海' + char) == max(0, score(before_typing, '海' + char) - 1) for char in shown)
                key(0xFF1B)
                result['feedback_episode_runtime'] = {'selected_plus_one': True, 'visible_two_pages_minus_one': True,
                    'unseen_unchanged': True, 'redraw_paging_unknown_letters_neutral': True,
                    'escape_once_and_continue_input': True, 'snapshot_version': after['version']}
                start_prediction('阿')
                before_focus = feedback_state()
                if args.focus_helper:
                    assert property('bihua_prediction_menu_active') == '1'
                if args.focus_helper:
                    helper = c.CDLL(str(args.focus_helper.resolve()))
                    focus_out = helper.ProbeFocusOut
                    focus_out.argtypes = [c.c_void_p, c.c_size_t]
                    focus_out.restype = None
                    get_api = bind('rime_get_api', c.c_void_p)
                    focus_out(get_api(), session)
                else:
                    set_property(session, b'bihua_feedback_neutral_boundary', b'focus_out')
                    clear(session)
                assert feedback_state() == before_focus, 'Neutral focus boundary deducted feedback'
                assert not snapshot()['candidates']
                assert property('bihua_prediction_menu_active') == ''
                result['feedback_episode_runtime']['neutral_focus_boundary'] = True
                if args.focus_helper:
                    key('h')
                    unfinished = snapshot()['preedit']
                    before_focus = feedback_state()
                    focus_out(get_api(), session)
                    assert snapshot()['preedit'] == unfinished and feedback_state() == before_focus
                    assert not read_commit(), 'FocusOut committed unfinished input'
                    key(0xFF1B)
                    result['feedback_episode_runtime']['native_focus_out_keeps_unfinished_composition'] = True
        if args.phrase_query:
            read_commit()
            assert property('bihua_phrase_load_status') == 'ok', property('bihua_phrase_load_status')
            clear(session)
            for letter in 'szfszh':
                key(letter)
            assert '中国' in snapshot()['candidates'] and '｜' in snapshot()['preedit'], snapshot()
            clear(session)
            for letter in 'htpn':
                key(letter)
            assert '天' in snapshot()['candidates'] and '？' in snapshot()['preedit'], snapshot()
            mobile_key_times = []
            if args.phone_phrases:
                for packed in ('s|s', 'sz|sz', 'szh|szh', 'szh|s?h'):
                    start = time.perf_counter()
                    current = query(packed)
                    mobile_key_times.append(round((time.perf_counter() - start) * 1000, 3))
                    assert current['candidates'] and not any(current['comments'])
                result['mobile_query_total_ms'] = mobile_key_times
            checked_words = 0
            for line in (user / 'bihua_personal_phrases.tsv').read_text(encoding='utf-8').splitlines():
                word, packed, _ = line.split('\t')
                assert word in query(packed)['candidates'], ('Full phrase missing', word)
                prefix = '|'.join(code[:2] for code in packed.split('|'))
                assert word in query(prefix)['candidates'], ('Phrase prefix missing', word)
                checked_words += 1
            clear(session)
            key(0xFFB6)
            key(0xFFB7)
            assert not snapshot()['preedit'] and not snapshot()['candidates']
            direct = query('sz|szh')['candidates']
            assert '中国' in direct, direct
            assert property('bihua_phrase_usage_中国') == str(args.expected_phrase_usage), 'Phrase usage did not survive process restart'
            key(str(direct.index('中国') + 1))
            assert read_commit() == '中国'
            direct = query('sz|szh')['candidates']
            assert property('bihua_phrase_usage_中国') == str(args.expected_phrase_usage + 1), (property('bihua_phrase_usage_中国'), property('bihua_phrase_storage_status'))
            wildcard = query('s?h|sz?h')['candidates']
            assert '中国' in wildcard, wildcard
            key(str(wildcard.index('中国') + 1))
            assert read_commit() == '中国'
            query('sz|szh')
            assert property('bihua_phrase_usage_中国') == str(args.expected_phrase_usage + 2)
            query('szhhshdh')
            assert property('bihua_alias_counts') == '', 'Phrase wildcard leaked into character aliases'
            wild_char = query('h?pn')['candidates']
            assert '天' in wild_char, wild_char
            if args.association_runtime:
                before_manual = int(property('bihua_manual_history_size'))
                key(str(wild_char.index('天') + 1))
                assert read_commit() == '天'
                assert int(property('bihua_manual_history_size')) == before_manual + 1, 'Manual wildcard character was excluded from history'
            query('s?|s?')
            assert int(property('bihua_query_lookups')) <= 120
            before_wildcard_limit = snapshot()['preedit']
            key('t')
            assert snapshot()['preedit'] == before_wildcard_limit, 'Third wildcard was accepted'
            query('sz|')
            before = snapshot()['preedit']
            key(0xFFB7)
            assert snapshot()['preedit'] == before, 'Double boundary was accepted'
            key(0xFF08)
            assert '|' not in snapshot()['preedit'], 'Backspace did not remove boundary'
            key(0xFF1B)
            assert not snapshot()['candidates']
            result['phrase_query'] = {'fixture_words_checked_full_and_prefix': checked_words, 'prefix': direct, 'wildcard': wildcard,
                                      'native_user_dictionary_count': args.expected_phrase_usage + 2, 'letter_f_t_keypad_6_7_and_editing': 'PASS'}
    finally:
        if session:
            destroy(session)
        finalize()
        assert static_hashes == {str(path.relative_to(user)): hashlib.sha256(path.read_bytes()).hexdigest() for path in static_paths}, 'Learning modified static profile files'
        result['static_profile_hashes_unchanged'] = True
        (user / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True, indent=2))
    faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    main()
