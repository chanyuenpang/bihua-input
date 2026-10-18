"""Canonical-code no-op saves and failure preservation in private directories."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

import personal_strokes as strokes

ROOT = Path(__file__).resolve().parent.parent


def table(folder, name='canonical_strokes', one='1'):
    folder.mkdir(parents=True, exist_ok=True)
    path=folder/(name+'.tsv')
    path.write_text('character\tstroke_digits\n一\t'+one+'\n丶\t4\n国\t25112141\n',encoding='utf-8')
    path.with_suffix('.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest(),encoding='ascii')
    return path


def main():
    with tempfile.TemporaryDirectory(prefix='bihua-stroke-save-') as temporary:
        sandbox=Path(temporary);data=sandbox/'data';source=table(data)
        user=sandbox/'user';user.mkdir()
        read_codes=strokes.canonical_codes
        def snapshot():
            return {p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in user.iterdir() if p.is_file() and p.name.startswith(strokes.NAME) and '.lock' not in p.name}
        with patch.object(strokes,'canonical_codes',lambda **_:read_codes(data)):
            for code in ['1','h','H']:
                result=strokes.action(user,'upsert',char='一',code=code)
                assert result['status']=='applied' and result['skipped_system'] and not result['changed'] and result['revision']==0
                assert not (user/strokes.NAME).exists() and not (user/(strokes.NAME+'.previous')).exists()
            strokes.action(user,'upsert',char='国',code='12345')
            before=snapshot();revision=strokes.read(user/strokes.NAME)[0]
            for char,code in [('一','1'),('丶','d'),('丶','N'),('丶','4')]:
                result=strokes.action(user,'upsert',char=char,code=code)
                assert result['skipped_system'] and result['revision']==revision and snapshot()==before
            strokes.action(user,'upsert',char='一',code='ss')
            before=snapshot();revision=strokes.read(user/strokes.NAME)[0]
            result=strokes.action(user,'upsert',char='一',code='h')
            assert result['skipped_system'] and result['code']=='ss' and result['revision']==revision and snapshot()==before
            result=strokes.action(user,'upsert',char='一',code='hs')
            assert result['changed'] and not result['skipped_system'] and result['revision']==revision+1
            result=strokes.action(user,'upsert',char='鼠',code='hspnz')
            assert result['changed'] and not result['skipped_system']
            before=snapshot();current=table(data,'current-canonical_strokes',one='11')
            current.write_text(current.read_text(encoding='utf-8')+'坏数据\n',encoding='utf-8')
            try:strokes.action(user,'upsert',char='一',code='1')
            except ValueError:pass
            else:raise AssertionError('Damaged current table silently fell back')
            assert snapshot()==before
            table(data,'current-canonical_strokes',one='11')
            result=strokes.action(user,'upsert',char='一',code='1')
            assert result['changed'] and not result['skipped_system']
            before=snapshot();result=strokes.action(user,'upsert',char='一',code='11')
            assert result['skipped_system'] and snapshot()==before

        dictionary=user/'bihua_local.dict.yaml'
        original='---\nname: bihua_local\n...\n一\thhhh\t1\n一\th\t1\n启\tnzhpszh\t1\n'
        dictionary.write_text(original,encoding='utf-8')
        manifest=user/'bihua_local.manifest.json'
        manifest.write_text(json.dumps({'generated_files':{dictionary.name:hashlib.sha256(dictionary.read_bytes()).hexdigest()}}),encoding='utf-8')
        def active_codes(**options):return read_codes(data,rime_directory=options.get('rime_directory'))
        with patch.object(strokes,'canonical_codes',active_codes):
            assert strokes.canonical_codes(rime_directory=user)['一']=='1111'
            before=snapshot();result=strokes.action(user,'upsert',char='一',code='1111')
            assert result['skipped_system'] and snapshot()==before
            result=strokes.action(user,'upsert',char='一',code='11')
            assert result['changed'] and not result['skipped_system']
            before=snapshot();result=strokes.action(user,'upsert',char='启',code='4513251')
            assert result['skipped_system'] and snapshot()==before
            assert dictionary.read_text(encoding='utf-8')==original
            dictionary.write_text(original+'国\th\t1\n',encoding='utf-8')
            try:strokes.action(user,'upsert',char='启',code='4513251')
            except ValueError:pass
            else:raise AssertionError('A corrupt active dictionary was ignored')
            assert snapshot()==before

        app=sandbox/'app';(app/'scripts').mkdir(parents=True);table(app/'data')
        for name in ['Manage-Personal.py','personal_strokes.py','personal_data.py']:
            shutil.copy2(ROOT/'scripts'/name,app/'scripts'/name)
        cli_user=sandbox/'cli-user';cli_user.mkdir();receipt=sandbox/'receipt.json'
        command=[sys.executable,'-B',str(app/'scripts/Manage-Personal.py'),'strokes','upsert','--rime-dir',str(cli_user),'--char=一','--codes=1','--json','--result-file',str(receipt)]
        output=subprocess.run(command,capture_output=True,check=True,encoding='utf-8')
        result=json.loads(output.stdout);ack=json.loads(receipt.read_text(encoding='utf-8'))
        assert result['skipped_system'] and ack['status']=='applied' and ack['skipped_system']
        assert not (cli_user/strokes.NAME).exists()
        quiet=subprocess.run([arg for arg in command if arg!='--json'],capture_output=True,check=True,encoding='utf-8')
        assert not quiet.stdout.strip() and not (cli_user/strokes.NAME).exists()
        proof={'result':'PASS','fresh_original_creates_no_record':True,'normalization_case_digits_dn':True,
               'existing_alias_revision_backup_and_mtime_unchanged':True,'different_and_unknown_code_still_saved':True,
               'current_table_preferred_and_corruption_preserves_data':True,'active_dictionary_overrides_stale_display_table':True,
               'default_dictionary_never_modified':True,'native_cli_receipt_noop_is_success':True,'no_success_message_for_original':True}
        (ROOT/'.verification/personal-save-0627.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
        print(json.dumps(proof))


if __name__=='__main__':main()
