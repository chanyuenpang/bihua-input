"""Local settings panel for the installed bihua_mvp schema. No desktop input."""
import argparse
import difflib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid

import yaml
from personal_data import atomic_write
from personal_strokes import canonical_codes
from key_bindings import ACTIONS, LETTER, KEYPAD, FIELDS as KEY_FIELDS, validate as validate_keys
import appearance

ROOT = Path(__file__).resolve().parent.parent
ASSETS = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}
DEPLOYER = Path('C:/Program Files/Rime/weasel-0.17.4/WeaselDeployer.exe')
spec = importlib.util.spec_from_file_location('personal_manager', Path(__file__).with_name('Manage-Personal.py'))
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)

class Loader(yaml.SafeLoader):
    pass


def mapping(loader, node):
    out = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in out:
            raise ValueError('配置文件有重复键，无法安全保存：' + str(key))
        out[key] = loader.construct_object(value_node)
    return out


Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


class Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def decode(text):
    value = yaml.load(text, Loader=Loader) or {}
    if not isinstance(value, dict):
        raise ValueError('配置文件必须为 YAML 映射')
    return value


def read(path):
    return path.read_bytes().decode('utf-8-sig') if path.exists() else ''


def get(config, path, default=None):
    value = config
    for key in path.split('/'):
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


REMOVE = object()

def patch_text(text, updates):
    original = decode(text)
    patch = original.get('patch', {})
    if not isinstance(patch, dict):
        raise ValueError('patch 不是映射，未修改配置')
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'
    positions = [i for i, line in enumerate(lines) if re.match(r'^patch:\s*(?:#.*)?$', line.rstrip())]
    if 'patch' in original and len(positions) != 1:
        raise ValueError('请将 patch 写成独立的 YAML 块；未修改配置')
    if not positions:
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += '\n'
        lines.append('patch:\n')
        positions = [len(lines) - 1]
    for key, value in updates.items():
        for parent in (key.split('/')[0],):
            if '/' in key and parent in patch:
                raise ValueError('存在嵌套的 ' + parent + ' patch，无法安全合并')
        start = end = None
        patch_start = positions[0]
        patch_end = len(lines)
        for i in range(patch_start + 1, len(lines)):
            if lines[i].strip() and not lines[i][0].isspace() and not lines[i].lstrip().startswith('#'):
                patch_end = i
                break
        for i in range(patch_start + 1, patch_end):
            if not re.match(r'^  \S', lines[i]) or lines[i].lstrip().startswith(('#', '-')):
                continue
            try:
                parsed = decode(lines[i].strip())
            except Exception:
                continue
            if key in parsed:
                start, end = i, i + 1
                while end < patch_end and (lines[end].startswith('    ') or not lines[end].strip()):
                    end += 1
                break
        if value is REMOVE:
            if start is not None:
                del lines[start:end]
            continue
        rendered = yaml.dump({key: value}, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=120)
        replacement = ['  ' + line for line in rendered.splitlines(keepends=True)]
        if start is None:
            lines[patch_end:patch_end] = replacement
        else:
            lines[start:end] = replacement
    result = ''.join(lines)
    after = decode(result)
    expected = dict(original)
    expected['patch'] = dict(patch)
    for key, value in updates.items():
        if value is REMOVE:
            expected['patch'].pop(key, None)
        else:
            expected['patch'][key] = value
    if after != expected:
        raise ValueError('配置合并校验失败，未修改配置')
    return result


BOOLS = ['page_minus', 'page_brackets', 'page_comma', 'page_tab', 'page_keypad', 'association', 'horizontal', 'mouse_input', 'stroke_info', 'arrow_navigation', 'copy_stroke', 'selection_stroke']
GROUPS = {'page_minus': [('minus', 'Page_Up'), ('equal', 'Page_Down')],
          'page_brackets': [('bracketleft', 'Page_Up'), ('bracketright', 'Page_Down')],
          'page_comma': [('comma', 'Page_Up'), ('period', 'Page_Down')],
          'page_tab': [('Shift+Tab', 'Page_Up'), ('ISO_Left_Tab', 'Page_Up'), ('Tab', 'Page_Down')],
          'page_keypad': [('KP_Subtract', 'Page_Up'), ('KP_Add', 'Page_Down')]}


class Settings:
    def __init__(self, directory, deploy=None):
        self.directory = directory
        self.paths = [directory / 'bihua_mvp.custom.yaml', directory / 'weasel.custom.yaml']
        self.lock = threading.Lock()
        self.previews = {}
        self.recovery_required = False
        self.deploy = deploy or self.real_deploy

    def real_deploy(self):
        executable = DEPLOYER
        native_receipt = Path(os.environ['LOCALAPPDATA']) / 'BihuaWeasel/installation.json'
        if native_receipt.exists():
            receipt = json.loads(native_receipt.read_text(encoding='utf-8'))
            candidate = Path(receipt['directory']) / 'WeaselDeployer.exe'
            allowed = (Path(os.environ['LOCALAPPDATA']) / 'BihuaWeasel').resolve()
            if receipt.get('status') == 'installed' and candidate.resolve().is_relative_to(allowed) and candidate.is_file():
                executable = candidate
        result = subprocess.run([str(executable), '/deploy'], shell=False, timeout=60,
                                creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
        if result.returncode:
            raise RuntimeError('小狼毫重新部署失败：' + str(result.returncode))

    def compiled(self):
        return decode(read(self.directory / 'build/bihua_mvp.schema.yaml'))

    def state(self):
        compiled = self.compiled()
        custom = decode(read(self.paths[0])).get('patch', {})
        style = decode(read(self.directory / 'build/weasel.yaml'))
        style_patch = decode(read(self.paths[1])).get('patch', {})
        def value(path, default=None):
            return custom.get(path, get(compiled, path, default))
        bindings = value('key_binder/bindings', [])
        settings = {'association': bool(value('bihua_matcher/personal_association', False)),
                    'prediction_pages': value('bihua_association/pages', 5),
                    'font_size': style_patch.get('style/font_point', get(style, 'style/font_point', 18)),
                    'horizontal': bool(style_patch.get('style/horizontal', get(style, 'style/horizontal', False))),
                    'mouse_input': bool(style_patch.get('bihua_mouse/enabled', get(style, 'bihua_mouse/enabled', False))),
                    'stroke_info': bool(style_patch.get('bihua_mouse/stroke_info', get(style, 'bihua_mouse/stroke_info', True))),
                    'copy_stroke': bool(style_patch.get('bihua_mouse/copy_stroke', get(style, 'bihua_mouse/copy_stroke', True))),
                    'selection_stroke': bool(style_patch.get('bihua_mouse/selection_stroke', get(style, 'bihua_mouse/selection_stroke', False))),
                    'arrow_navigation': bool(style_patch.get('bihua_mouse/arrow_navigation', get(style, 'bihua_mouse/arrow_navigation', True)))}
        settings.update(appearance.values(style,style_patch))
        shared={} if style.get('preset_color_schemes') else decode(re.sub(r'\t(?=\s*#)',' ',read(ROOT/'data/weasel.yaml')))
        schemes=appearance.catalog(style,shared,[settings['color_scheme'],settings['dark_scheme']])
        for name, keys in GROUPS.items():
            settings[name] = all(any(row.get('accept') == key and row.get('send') == send and row.get('when') == 'has_menu' for row in bindings) for key, send in keys if key != 'ISO_Left_Tab')
        settings['page_keypad'] = bool(value('bihua_keys/page_keypad', True))
        for device, presets in [('letter', LETTER), ('keypad', KEYPAD)]:
            settings[device+'_style'] = str(value('bihua_keys/'+device+'_style', 'standard'))
            settings[device+'_keys'] = value('bihua_keys/'+device, presets['standard'].copy())
        from key_bindings import migrate_keypad
        settings['keypad_style'],settings['keypad_keys']=migrate_keypad(settings['keypad_style'],settings['keypad_keys'])
        rows = manager.phrase_rows(self.directory / 'bihua_personal_phrases.tsv')
        words = [{'text': text, 'digits': '|'.join(codes).translate(str.maketrans('hspnz', '12345'))} for text, (codes, _) in sorted(rows.items())]
        return {'settings': settings, 'version': str(get(compiled, 'schema/version', '未部署')),
                'phrase_enabled': bool(value('bihua_matcher/phrase_enabled', False)), 'words': words,
                'appearance': {'schemes':schemes},
                'recovery_required': self.recovery_required}

    def preview(self, settings):
        if set(settings) != set(BOOLS + ['prediction_pages', 'font_size', *KEY_FIELDS,*appearance.FIELDS]):
            raise ValueError('设置字段不完整或包含未知字段')
        key_settings = validate_keys(settings)
        if any(type(settings[key]) is not bool for key in BOOLS):
            raise ValueError('开关值必须是布尔值')
        for key, low, high in [('prediction_pages', 1, 5), ('font_size', 8, 72)]:
            if type(settings[key]) is not int or not low <= settings[key] <= high:
                raise ValueError('设置范围错误：' + key)
        existing = [read(path) for path in self.paths]
        style_updates=appearance.updates(settings,self.state()['appearance']['schemes'])
        style_updates['bihua_mouse/enabled']=settings['mouse_input']
        style_updates['bihua_mouse/stroke_info']=settings['stroke_info']
        style_updates['bihua_mouse/copy_stroke']=settings['copy_stroke']
        style_updates['bihua_mouse/selection_stroke']=settings['selection_stroke']
        style_updates['bihua_mouse/arrow_navigation']=settings['arrow_navigation']
        style_patch=decode(existing[1]).get('patch',{})
        compiled = self.compiled()
        patch = decode(existing[0]).get('patch', {})
        bindings = patch.get('key_binder/bindings', get(compiled, 'key_binder/bindings', []))
        owned = {key for group in GROUPS.values() for key, _ in group}
        owned.update(['Return', 'KP_Enter', 'KP_0', 'KP_6', 'KP_7', 'KP_8', 'KP_9',
                      'KP_1', 'KP_2', 'KP_3', 'KP_4', 'KP_5', 'd'])
        bindings = [row for row in bindings if row.get('accept') not in owned]
        bindings += [{'when': 'has_menu', 'accept': key, 'send': 'space'} for key in ['Return', 'KP_Enter', 'KP_0']]
        for name, keys in GROUPS.items():
            if settings[name]:
                bindings += [{'when': 'has_menu', 'accept': key, 'send': send} for key, send in keys]
        updates = {'bihua_matcher/fuzzy_enabled': REMOVE, 'bihua_matcher/learning_enabled': REMOVE,
                   'bihua_matcher/personal_association': settings['association'],
                   'bihua_matcher/static_association': settings['association'],
                   'bihua_association/pages': settings['prediction_pages'],
                   'bihua_association/half_life_days': REMOVE,
                   'key_binder/import_preset': None,
                   'key_binder/bindings': bindings, 'menu/page_size': 9}
        for device in ('letter','keypad'):
            updates['bihua_keys/'+device] = key_settings[device+'_keys']
            updates['bihua_keys/'+device+'_style'] = key_settings[device+'_style']
        updates['bihua_keys/page_keypad'] = settings['page_keypad']
        changed = [patch_text(existing[0], updates), patch_text(existing[1], {key:value for key,value in style_updates.items() if style_patch.get(key,REMOVE)!=value})]
        identity = secrets.token_urlsafe(20)
        self.previews[identity] = (time.monotonic(), existing, changed, updates,style_updates)
        self.previews = {key: item for key, item in self.previews.items() if time.monotonic() - item[0] < 600}
        diff = ''.join(''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile=path.name, tofile=path.name)) for path, old, new in zip(self.paths, existing, changed))
        return {'preview_id': identity, 'diff': diff or '配置没有变化，将重新部署以加载个人词库。'}

    def apply(self, identity):
        with self.lock:
            if self.recovery_required:
                raise RuntimeError('上次回滚未完成，请先恢复配置；暂时禁止继续保存')
            item = self.previews.pop(identity, None)
            if not item or time.monotonic() - item[0] >= 600:
                raise ValueError('预览已过期，请重新预览')
            _, existing, changed, updates,style_updates = item
            if [read(path) for path in self.paths] != existing:
                raise RuntimeError('配置刚被其他程序修改，请刷新后重试')
            backup = self.directory / 'bihua-settings-backups' / uuid.uuid4().hex
            backup.mkdir(parents=True)
            existed = [path.exists() for path in self.paths]
            for path, old, present in zip(self.paths, existing, existed):
                if present:
                    (backup / path.name).write_bytes(path.read_bytes())
            try:
                for path, new in zip(self.paths, changed):
                    atomic_write(path, new)
                self.deploy()
                compiled = self.compiled()
                for key in ['bihua_matcher/personal_association', 'bihua_matcher/static_association', 'bihua_association/pages', 'menu/page_size']:
                    if get(compiled, key) != updates[key]:
                        raise RuntimeError('编译配置未加载设置：' + key)
                for key in ('bihua_keys/letter','bihua_keys/keypad','bihua_keys/letter_style','bihua_keys/keypad_style','bihua_keys/page_keypad'):
                    actual=get(compiled,key)
                    if key.endswith('_style'): actual=str(actual)
                    if actual != updates[key]:
                        raise RuntimeError('编译配置未加载按键：'+key)
                paging_keys = {key for group in GROUPS.values() for key, _ in group}
                expected = [row for row in updates['key_binder/bindings'] if row.get('accept') in paging_keys]
                actual = [row for row in get(compiled, 'key_binder/bindings', []) if row.get('accept') in paging_keys]
                if actual != expected:
                    raise RuntimeError('翻页快捷键未按设置加载')
                for key in ['Return', 'KP_Enter', 'KP_0']:
                    if {'when': 'has_menu', 'accept': key, 'send': 'space'} not in get(compiled, 'key_binder/bindings', []):
                        raise RuntimeError('确认键未加载：' + key)
                compiled_style = decode(read(self.directory / 'build/weasel.yaml'))
                for key,expected in style_updates.items():
                    actual=get(compiled_style,key)
                    if key in ('style/color_scheme','style/color_scheme_dark'):actual=str(actual)
                    if actual != expected:
                        raise RuntimeError('候选栏外观未加载：' + key)
            except Exception as error:
                try:
                    for path, old, present in zip(self.paths, existing, existed):
                        if present:
                            atomic_write(path, old)
                        else:
                            path.unlink(missing_ok=True)
                    self.deploy()
                except Exception as rollback:
                    self.recovery_required = True
                    raise RuntimeError(f'{error}；回滚未完成：{rollback}。备份：{backup}') from error
                raise RuntimeError(f'{error}；已恢复原配置。备份：{backup}') from error
            return {'message': '设置已保存并应用。切回「笔画输入法」即可使用。'}

    def word_action(self, action, data):
        args = [sys.executable, str(ROOT / 'scripts/Manage-Personal.py'), 'phrases', action, '--rime-dir', str(self.directory)]
        temporary = None
        if action == 'add':
            word = str(data['text'])
            codes = re.sub(r'\s+', '', str(data.get('codes', '')))
            if not codes:
                standard = canonical_codes(rime_directory=self.directory)
                if any(char not in standard for char in word):
                    raise ValueError('该词有未收录的字，请手动填写标准笔画编码')
                codes = '|'.join(standard[char] for char in word)
            args += ['--word=' + word, '--codes=' + codes]
        elif action == 'delete':
            args += ['--word=' + str(data['text'])]
        elif action == 'import':
            temporary = ROOT / '.verification' / ('panel-import-' + uuid.uuid4().hex + '.tsv')
            atomic_write(temporary, str(data['content']))
            args += ['--input', str(temporary)]
        else:
            raise ValueError('未知词库操作')
        try:
            result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                    timeout=20, shell=False, creationflags=subprocess.CREATE_NO_WINDOW,
                                    env=dict(os.environ, PYTHONUTF8='1'))
            if result.returncode:
                raise ValueError(result.stderr.strip().splitlines()[-1])
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        return {'message': '个人词库已保存'}

    def stroke_action(self, action, data=None):
        import personal_strokes
        data=data or {}
        result=personal_strokes.action(self.directory,action,char=data.get('text'),code=data.get('code'),
                                       content=data.get('content'),replace=bool(data.get('replace',False)))
        standard=canonical_codes(rime_directory=self.directory)
        for row in result['rows']:row['system_digits']=standard.get(row['text'],'')
        return result


def make_server(service, token, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, body, content_type='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            host = '127.0.0.1:' + str(self.server.server_port)
            origin = self.headers.get('Origin')
            if self.headers.get('Host') != host or (origin and origin != 'http://' + host):
                self.send(403, {'error': '请求来源不允许'})
                return False
            if self.path.startswith('/api/') and not secrets.compare_digest(self.headers.get('X-Bihua-Token', ''), token):
                self.send(403, {'error': '设置面板会话已失效，请重新打开面板'})
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            try:
                if self.path in ASSETS:
                    name = ASSETS[self.path]
                    mime = {'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css'}[name.rsplit('.', 1)[1]]
                    self.send(200, (ROOT / 'settings' / name).read_bytes(), mime + '; charset=utf-8')
                elif self.path == '/api/state':
                    self.send(200, service.state())
                elif self.path == '/api/words/export':
                    self.send(200, {'content': read(service.directory / 'bihua_personal_phrases.tsv')})
                else:
                    self.send(404, {'error': '未找到页面'})
            except Exception as error:
                self.send(400, {'error': str(error)})

        def do_POST(self):
            if not self.authorized():
                return
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 2 * 1024 * 1024 or self.headers.get_content_type() != 'application/json':
                    self.send(413, {'error': '请求格式或大小不符合要求'})
                    return
                data = json.loads(self.rfile.read(length))
                if self.path == '/api/preview':
                    self.send(200, service.preview(data))
                elif self.path == '/api/save':
                    self.send(200, service.apply(data['preview_id']))
                elif self.path in ['/api/words/add', '/api/words/delete', '/api/words/import']:
                    self.send(200, service.word_action(self.path.rsplit('/', 1)[1], data))
                else:
                    self.send(404, {'error': '未知操作'})
            except Exception as error:
                self.send(400, {'error': str(error)})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rime-dir', type=Path, default=Path(os.environ['APPDATA']) / 'Rime')
    parser.add_argument('--session-file', type=Path)
    parser.add_argument('--reuse-session', action='store_true')
    args = parser.parse_args()
    token = secrets.token_urlsafe(32)
    port = 0
    if args.reuse_session:
        from urllib.parse import urlsplit
        previous = json.loads(args.session_file.read_text(encoding='utf-8'))
        address = urlsplit(previous['url'])
        if address.scheme != 'http' or address.hostname != '127.0.0.1' or address.username or len(address.fragment) < 16:
            raise ValueError('Cannot reuse an invalid local settings session')
        token, port = address.fragment, address.port
    server = make_server(Settings(args.rime_dir.resolve()), token, port)
    session = {'pid': os.getpid(), 'url': f'http://127.0.0.1:{server.server_port}/#{token}'}
    if args.session_file:
        atomic_write(args.session_file, json.dumps(session))
    print(json.dumps(session), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
