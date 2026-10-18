"""Appearance persistence, dark-mode selection, previews and rollback contracts."""
from pathlib import Path
import importlib.util
import json
import tempfile
import sys
import yaml

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
import appearance
spec=importlib.util.spec_from_file_location('panel',ROOT/'scripts/Settings-Panel.py')
panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
with tempfile.TemporaryDirectory(prefix='appearance-test-',dir=ROOT/'.verification') as tmp:
    user=Path(tmp);(user/'build').mkdir()
    schema={'schema':{'version':'test'},'key_binder':{'bindings':[]}}
    original_style={'style':{'color_scheme':'ink','font_face':'Microsoft YaHei','font_point':18},
                    'preset_color_schemes':{'ink':{'name':'墨池','back_color':0xffffff,'hilited_candidate_back_color':0},
                       'aqua':{'name':'碧水','back_color':0xeceeee,'hilited_candidate_back_color':0xfa3a0a},
                       123456:{'name':'自定义数字名称','back_color':0x332211}}}
    (user/'build/bihua_mvp.schema.yaml').write_text(yaml.safe_dump(schema),encoding='utf-8')
    (user/'build/weasel.yaml').write_text(yaml.safe_dump(original_style,allow_unicode=True),encoding='utf-8')
    (user/'weasel.custom.yaml').write_text('# preserve\npatch:\n  custom/value: untouched\n  "style/color_scheme": ink # keep\n',encoding='utf-8')
    def put_path(target,key,value):
        parts=key.split('/')
        for part in parts[:-1]:target=target.setdefault(part,{})
        target[parts[-1]]=value
    def deploy():
        compiled=json.loads(json.dumps(schema));style=json.loads(json.dumps(original_style))
        for path,base in [('bihua_mvp.custom.yaml',compiled),('weasel.custom.yaml',style)]:
            for key,value in panel.decode(panel.read(user/path)).get('patch',{}).items():put_path(base,key,value)
        (user/'build/bihua_mvp.schema.yaml').write_text(yaml.safe_dump(compiled),encoding='utf-8')
        (user/'build/weasel.yaml').write_text(yaml.safe_dump(style,allow_unicode=True),encoding='utf-8')
    service=panel.Settings(user,deploy);start=service.state()
    assert {r['id'] for r in start['appearance']['schemes']}=={'ink','aqua','123456'}
    settings=dict(start['settings'],color_scheme='aqua',dark_scheme='ink',font_face='微软雅黑',font_size=22,
                  horizontal=True,corner_radius=12,candidate_spacing=9)
    before=(user/'weasel.custom.yaml').read_bytes();preview=service.preview(settings)
    assert (user/'weasel.custom.yaml').read_bytes()==before
    service.apply(preview['preview_id']);assert service.state()['settings']==settings
    loaded=panel.decode(panel.read(user/'build/weasel.yaml'))
    assert panel.get(loaded,'style/color_scheme')=='aqua' and panel.get(loaded,'style/color_scheme_dark')=='ink'
    assert panel.get(loaded,'style/font_face')==panel.get(loaded,'style/label_font_face')=='微软雅黑'
    assert panel.get(loaded,'style/layout/corner_radius')==12
    assert 'custom/value: untouched' in panel.read(user/'weasel.custom.yaml')
    saved=(user/'weasel.custom.yaml').read_bytes();calls=0
    def fail_once():
        global calls
        calls+=1
        if calls==1:raise RuntimeError('appearance deployment failure')
        deploy()
    service.deploy=fail_once
    try:service.apply(service.preview(dict(settings,color_scheme='ink'))['preview_id']);raise AssertionError('failure hidden')
    except RuntimeError as error:assert '已恢复原配置' in str(error)
    assert (user/'weasel.custom.yaml').read_bytes()==saved
    service.deploy=deploy
    service.apply(service.preview(dict(settings,color_scheme='123456',dark_scheme=''))['preview_id'])
    assert service.state()['settings']['color_scheme']=='123456' and service.state()['settings']['dark_scheme']==''
    for bad in [dict(settings,color_scheme='unknown'),dict(settings,font_face='bad\nfont'),dict(settings,corner_radius=-1)]:
        try:service.preview(bad);raise AssertionError('bad style accepted')
        except ValueError:pass
assert appearance.color(0xfa3a0a)=='#0a3afa'
assert appearance.color(0xff123456,'argb')=='#123456'
assert appearance.color(0x123456ff,'rgba')=='#123456'
result={'result':'PASS','themes_and_dark_mode':True,'unicode_font':True,'numeric_theme_identity':True,
        'font_layout_readback':True,'preview_no_write':True,'rollback_preserves_bytes':True,'color_preview_formats':True}
(ROOT/'.verification/appearance-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
