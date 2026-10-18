"""Real Rime hot-alias queries and atomic personal-stroke transactions in isolation."""
from pathlib import Path
import ctypes as c
import importlib.util
import json
import os
import shutil
import sys
import uuid
from unittest.mock import patch
import yaml
import personal_strokes as strokes

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('abi',ROOT/'scripts/Test-Rime.py')
abi=importlib.util.module_from_spec(spec);spec.loader.exec_module(abi)

def main():
    user=ROOT/'.verification'/('personal-strokes-'+uuid.uuid4().hex);user.mkdir(parents=True)
    path=user/strokes.NAME
    result=strokes.action(user,'upsert',char='中',code='43123');assert result['revision']==1
    assert not strokes.action(user,'upsert',char='中',code='nphsp')['changed']
    before=path.read_bytes()
    for content in ['中\thh\n中\tss\n','中\t16\n','中国\th\n']:
        try:strokes.action(user,'import',content=content)
        except ValueError:pass
        else:raise AssertionError('invalid batch accepted')
        assert path.read_bytes()==before
    original=strokes.atomic_write
    def fail_replace(destination,text):
        if destination==path:raise OSError('injected write failure')
        original(destination,text)
    with patch.object(strokes,'atomic_write',fail_replace):
        try:strokes.action(user,'upsert',char='国',code='pphssh')
        except OSError:pass
        else:raise AssertionError('write failure swallowed')
    assert path.read_bytes()==before
    with strokes.association_lock(path):
        try:strokes.action(user,'upsert',char='国',code='pphssh')
        except RuntimeError:pass
        else:raise AssertionError('concurrent writer accepted')
    strokes.action(user,'upsert',char='国',code='pphssh')
    # A public profile only. No installed dictionary or user history is copied.
    profile=ROOT/'.verification/open-profile';(user/'lua').mkdir()
    for source in (ROOT/'rime/lua').glob('*.lua'):shutil.copy2(source,user/'lua'/source.name)
    for source in profile.glob('*.lua'):shutil.copy2(source,user/'lua'/source.name)
    shutil.copy2(profile/'bihua_local.dict.yaml',user)
    shutil.copy2(profile/'bihua_local.manifest.json',user)
    schema=yaml.safe_load((ROOT/'rime/bihua_local.schema.yaml').read_text(encoding='utf-8'))
    schema['engine']['processors'].insert(0,'lua_processor@*bihua_query_keys')
    schema['engine']['segmentors'].insert(0,'lua_segmentor@*bihua_query_segmentor')
    schema['bihua_matcher'].update(phrase_enabled=True,mobile_phrases=True)
    schema['bihua_phrase']={'dictionary':'bihua_local','user_dict':'test_phrases'}
    (user/'bihua_local.schema.yaml').write_text(yaml.safe_dump(schema,allow_unicode=True),encoding='utf-8')
    (user/'default.custom.yaml').write_text('patch:\n  schema_list: [{schema: bihua_local}]\n',encoding='utf-8')
    system={}
    for line in (profile/'canonical_strokes.tsv').read_text(encoding='utf-8').splitlines()[1:]:
        if '\t' in line:
            char,code=line.split('\t');system[char]=code.translate(str.maketrans('12345','hspnz'))
    (user/'bihua_personal_phrases.tsv').write_text('中国\t'+system['中']+'|'+system['国']+'\t1\n',encoding='utf-8')
    app=Path(os.environ['LOCALAPPDATA'])/'BihuaWeasel/0.6.21'
    dll=c.CDLL(str(app/'rime.dll'))
    def bind(name,result,*types):
        fn=getattr(dll,name);fn.restype=result;fn.argtypes=list(types);return fn
    setup=bind('RimeSetup',None,c.POINTER(abi.Traits));init=bind('RimeInitialize',None,c.POINTER(abi.Traits));final=bind('RimeFinalize',None)
    traits=abi.initialized(abi.Traits);traits.shared_data_dir=str(app/'data').encode();traits.user_data_dir=str(user).encode();traits.app_name=b'rime.personal_strokes_test';traits.log_dir=b'';traits.min_log_level=2
    setup(c.byref(traits));init(c.byref(traits))
    maintain=bind('RimeStartMaintenance',c.c_int,c.c_int);join=bind('RimeJoinMaintenanceThread',None)
    create=bind('RimeCreateSession',c.c_size_t);select=bind('RimeSelectSchema',c.c_int,c.c_size_t,c.c_char_p)
    clear=bind('RimeClearComposition',None,c.c_size_t);key=bind('RimeProcessKey',c.c_int,c.c_size_t,c.c_int,c.c_int)
    ctx=bind('RimeGetContext',c.c_int,c.c_size_t,c.POINTER(abi.Context));free=bind('RimeFreeContext',None,c.POINTER(abi.Context))
    prop=bind('RimeGetProperty',c.c_int,c.c_size_t,c.c_char_p,c.c_char_p,c.c_size_t)
    try:
        maintain(1);join();session=create();assert select(session,b'bihua_local')
        def query(code):
            clear(session)
            for char in code:key(session,{'|':0xffb7,'?':0xffb6}.get(char,ord(char)),0)
            value=abi.initialized(abi.Context);assert ctx(session,c.byref(value))
            try:return {'preedit':abi.text(value.composition.preedit),'candidates':[abi.text(value.menu.candidates[i].text) for i in range(value.menu.num_candidates)]}
            finally:free(c.byref(value))
        cases={}
        for code,expected in [('nphsp','中'),('nph','中'),('np?sp','中'),('nph|pph','中国'),('szh|pph','中国'),('nph|'+system['国'],'中国'),(system['中'],'中')]:
            cases[code]=query(code);assert expected in cases[code]['candidates'],(code,cases[code])
        before=query('nph');strokes.action(user,'upsert',char='国',code='pphsshh')
        value=abi.initialized(abi.Context);ctx(session,c.byref(value));assert abi.text(value.composition.preedit)==before['preedit'];free(c.byref(value))
        assert '国' in query('pphsshh')['candidates']
        revision,rows=strokes.read(path)
        path.write_text(strokes.HEADER+'\t'+str(revision+1)+'\n中\tinvalid\n',encoding='utf-8')
        assert '中' in query('nphsp')['candidates']
        status=c.create_string_buffer(256);prop(session,b'bihua_personal_stroke_load_status',status,len(status));assert status.value==b'invalid_batch',status.value
        path.write_text(strokes.render(revision+2,rows),encoding='utf-8')
        strokes.action(user,'delete',char='中')
        assert '中' not in query('nphsp')['candidates']
        assert '中' in query(system['中'])['candidates']
        # Remove personal phrases to verify the independent built-in tail path.
        (user/'bihua_personal_phrases.tsv').unlink()
        strokes.action(user,'upsert',char='中',code='nphsp')
        session=create();assert select(session,b'bihua_local')
        assert '中国' in query('nph|pph')['candidates']
        # New sessions see the same current snapshot without maintenance/deploy.
        session=create();assert select(session,b'bihua_local');assert '国' in query('pphsshh')['candidates']
        result={'result':'PASS','atomic_validation_lock_failure':True,'direct_prefix_wildcard_phrase_and_system_coexist':cases,'built_in_phrase_aliases':True,'hot_save_keeps_composition':True,'invalid_revision_last_good':True,'delete_and_new_session':True,'deployer_called':False,'sandbox':str(user)}
        (ROOT/'.verification/personal-strokes-tests.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
    finally:final()

if __name__=='__main__':main()
