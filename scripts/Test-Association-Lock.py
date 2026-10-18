"""Private real-Rime process-lock and cross-process decay verification; no UI."""
import argparse
import ctypes as c
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from personal_data import association_lock, lock_name

ROOT = Path(__file__).resolve().parent.parent


def worker(args):
    spec = importlib.util.spec_from_file_location('rime_abi', Path(__file__).with_name('Test-Rime.py'))
    abi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(abi)
    dll = c.CDLL(str(Path(args.dll).resolve()))

    def bind(name, result, *parameters):
        fn = getattr(dll, name)
        fn.restype, fn.argtypes = result, list(parameters)
        return fn

    setup = bind('RimeSetup', None, c.POINTER(abi.Traits))
    initialize = bind('RimeInitialize', None, c.POINTER(abi.Traits))
    finalize = bind('RimeFinalize', None)
    create = bind('RimeCreateSession', c.c_size_t)
    destroy = bind('RimeDestroySession', c.c_int, c.c_size_t)
    select = bind('RimeSelectSchema', c.c_int, c.c_size_t, c.c_char_p)
    prop = bind('RimeGetProperty', c.c_int, c.c_size_t, c.c_char_p, c.c_char_p, c.c_size_t)
    traits = abi.initialized(abi.Traits)
    traits.shared_data_dir = str(Path(args.shared).resolve()).encode()
    traits.user_data_dir = str(args.worker.resolve()).encode()
    traits.app_name = b'rime.bihua_lock_test'
    traits.min_log_level = 2
    setup(c.byref(traits))
    initialize(c.byref(traits))
    session = 0
    try:
        if args.prepare:
            maintenance = bind('RimeStartMaintenance', c.c_int, c.c_int)
            join = bind('RimeJoinMaintenanceThread', None)
            maintenance(1)
            join()
        session = create()
        assert session and select(session, b'lock_probe')
        buffer = c.create_string_buffer(8192)
        assert prop(session, b'lock_probe', buffer, len(buffer))
        result = json.loads(buffer.value.decode())
        print(json.dumps(result, ensure_ascii=True), flush=True)
        if args.hold:
            input()  # Parent owns this process handle and releases it explicitly.
    finally:
        if session:
            destroy(session)
        finalize()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dll', required=True)
    parser.add_argument('--shared', required=True)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--hold', action='store_true')
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if args.worker:
        if not args.worker.resolve().is_relative_to((ROOT / '.verification').resolve()):
            raise ValueError('Only private verification directories are permitted')
        return worker(args)
    directory = ROOT / '.verification' / ('association-lock-' + uuid.uuid4().hex)
    (directory / 'lua').mkdir(parents=True)
    for name in ('bihua_association_core.lua', 'bihua_association_store.lua', 'bihua_json.lua'):
        shutil.copy2(ROOT / 'rime/lua' / name, directory / 'lua')
    (directory / 'lock_probe.schema.yaml').write_text('''schema:
  schema_id: lock_probe
  name: Private lock probe
  version: "1"
engine:
  processors: [express_editor]
  segmentors: [abc_segmentor]
  translators: [lua_translator@*lock_probe]
''', encoding='utf-8')
    (directory / 'default.custom.yaml').write_text('patch:\n  schema_list:\n    - schema: lock_probe\n', encoding='utf-8')
    (directory / 'lua/lock_probe.lua').write_text('''local Store = require("bihua_association_store")
local Json = require("bihua_json")
local report
return {init=function(env)
  if not report then
    local owner = Store.open(rime_api.get_user_data_dir() .. "/personal.jsonl")
    report = {status=owner.status, read_only=owner.read_only}
    if owner.lock then
      local now = next(owner.state.confirmed) and 1010 or 1000
      owner.state.clock = function() return now end
      if not next(owner.state.confirmed) then
        owner.state:observe("甲", "manual_stroke_char")
        owner.state:observe("乙", "manual_stroke_char")
        owner.state:boundary()
        owner.state:observe("甲", "manual_stroke_char")
        assert(owner.state:select(owner.state:query(5)[1], true))
        owner.state:clear_window()
        assert(Store.save(owner))
        report.created = true
      else
        owner.state:boundary()
        owner.state:observe("甲", "manual_stroke_char")
        report.score_after_restart = owner.state:query(5)[1].score
        now = 999999
        report.score_after_time = owner.state:query(5)[1].score
        report.last_feedback_at = owner.state.confirmed["甲乙"].last_feedback_at
        for i=1,11 do
          owner.state:boundary();owner.state:observe("甲", "manual_stroke_char")
          owner.state:ignore({owner.state:query(5)[1]})
        end
        owner.state:boundary();owner.state:observe("甲", "manual_stroke_char")
        report.hidden = #owner.state:query(5) == 0
        assert(Store.save(owner))
      end
    else
      report.write_rejected = not Store.save(owner)
    end
  end
  env.engine.context:set_property("lock_probe", Json.encode(report))
end, func=function() end}
''', encoding='utf-8')
    command = [sys.executable, str(Path(__file__).resolve()), '--dll', args.dll,
               '--shared', args.shared, '--worker', str(directory)]
    first = subprocess.Popen(command + ['--hold', '--prepare'], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    try:
        a = json.loads(first.stdout.readline())
        assert a.get('created') and not a['read_only'], a
        path = directory / 'personal.jsonl'
        before = path.read_bytes()
        second = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        assert second.returncode == 0, second.stderr
        b = json.loads(second.stdout)
        assert b['read_only'] and b['write_rejected'] and b['status'] == 'lock_busy_or_unavailable', b
        assert path.read_bytes() == before, 'Rejected writer changed the personal snapshot'
        try:
            with association_lock(path):
                raise AssertionError('Offline manager ignored native Rime lock: ' + repr(a) + '; python=' + lock_name(path))
        except RuntimeError:
            pass
    finally:
        output, errors = first.communicate('\n', timeout=30)
        assert first.returncode == 0, output + errors
    with association_lock(path):
        blocked = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        assert blocked.returncode == 0 and json.loads(blocked.stdout)['read_only'], blocked.stderr
    third = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    assert third.returncode == 0, third.stderr
    after = json.loads(third.stdout)
    assert after['score_after_restart'] == 11 and after['score_after_time'] == 11 and after['hidden'] and after['last_feedback_at'] == 1000, after
    report = {'result': 'PASS', 'owner_process': a, 'concurrent_process': b,
              'after_owner_exit': after, 'concurrent_writer_left_snapshot_unchanged': True,
              'offline_manager_native_lock_both_directions': 'PASS',
              'private_user_directory': str(directory)}
    (directory / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
