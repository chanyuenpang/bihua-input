"""Run the real PowerShell extractor against owned Windows fault fixtures."""
from pathlib import Path
import ctypes as c
from ctypes import wintypes as w
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
PS = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
kernel = c.WinDLL('kernel32', use_last_error=True)
kernel.CreateFileW.argtypes = [w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE]
kernel.CreateFileW.restype = w.HANDLE
kernel.CloseHandle.argtypes = [w.HANDLE]
cases = []

def opened(path, access=1, flags=0x02000000, share=3):
    handle = kernel.CreateFileW(str(path),access,share,None,3,flags,None)
    assert handle != w.HANDLE(-1).value, c.get_last_error()
    return handle

with tempfile.TemporaryDirectory(prefix='bihua-extract-test-',dir=ROOT/'.verification') as temporary:
    base = Path(temporary)
    script = base/'extract.ps1'
    script.write_bytes(b'\xef\xbb\xbf'+(ROOT/'packaging/Extract-Payload.ps1').read_bytes())
    archive = base/'payload.zip'
    files = {'python/python.exe':b'owned fixture, never executed', 'scripts/example.txt':'中文测试'.encode()}
    manifest = {'product':'BihuaInput','version':'test','files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}
    with zipfile.ZipFile(archive,'w') as z:
        for name,data in files.items():z.writestr(name,data)
        z.writestr('release-manifest.json',json.dumps(manifest))
    fingerprint = hashlib.sha256(archive.read_bytes()).hexdigest()
    def run(target, success=True, needle=None, package=archive, identity=fingerprint):
        result = subprocess.run([str(PS),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),
            '-Archive',str(package),'-Destination',str(target),'-Fingerprint',identity,'-Version','test'],
            env=dict(os.environ,PSModulePath=''),capture_output=True,timeout=30)
        output = (result.stdout+result.stderr).decode('utf-8-sig',errors='replace')
        assert (result.returncode==0)==success,output
        if needle:assert needle in output,output
        return output

    target = base/'占用目录'
    (target/'python').mkdir(parents=True)
    (target/'.bihua-payload-state').write_text('extracting '+fingerprint)
    handle = opened(target/'python')
    try:
        try:target.rename(base/'renamed');raise AssertionError('expected Windows rename refusal')
        except OSError as error:assert error.winerror in (5,32),error
        run(target)
        for name,data in files.items():assert (target/name).read_bytes()==data
    finally:kernel.CloseHandle(handle)
    cases.append('directory rename denied while extraction succeeds')
    before={n:(target/n).stat().st_mtime_ns for n in files}
    run(target)
    assert before=={n:(target/n).stat().st_mtime_ns for n in files}
    cases.append('completed payload verified without rewriting')
    (target/'python/python.exe').write_bytes(b'corrupt')
    run(target,False,'安装文件损坏')
    assert (target/'python/python.exe').read_bytes()==b'corrupt'
    cases.append('corrupt completed payload rejected without overwrite')

    partial=base/'partial';(partial/'python').mkdir(parents=True)
    (partial/'.bihua-payload-state').write_text('extracting '+fingerprint)
    blocked=partial/'python/python.exe';blocked.write_bytes(b'incomplete')
    handle=opened(blocked,access=0x80000000,flags=0,share=1)
    try:
        run(partial,False)
        assert (partial/'.bihua-payload-state').read_text()=='extracting '+fingerprint
        assert not (partial/'release-manifest.json').exists()
    finally:kernel.CloseHandle(handle)
    run(partial)
    assert (partial/'.bihua-payload-state').read_text()=='ready '+fingerprint
    assert blocked.read_bytes()==files['python/python.exe']
    cases.append('write failure leaves partial state and can resume')

    foreign=base/'foreign';foreign.mkdir();(foreign/'release-manifest.json').write_text('{}')
    sentinel=foreign/'keep.txt';sentinel.write_text('must remain')
    run(foreign,False,'已有其他文件')
    assert sentinel.read_text()=='must remain' and (foreign/'release-manifest.json').read_text()=='{}'
    cases.append('foreign directory and fake manifest preserved')
    (foreign/'.bihua-payload-state').write_text('extracting another-package')
    run(foreign,False,'已有其他文件')
    assert sentinel.read_text()=='must remain'
    cases.append('different package cannot resume another payload')
    run(base/'bad-archive',False,'资源校验失败',identity='0'*64)
    assert not (base/'bad-archive').exists()
    cases.append('archive hash checked before destination changes')

    invalid=base/'invalid.zip'
    with zipfile.ZipFile(invalid,'w') as z:
        z.writestr('release-manifest.json',json.dumps({'product':'BihuaInput','version':'test','files':{'../escape.txt':'0'*64}}))
        z.writestr('../escape.txt','never written')
    run(base/'unsafe',False,'路径无效',package=invalid,identity=hashlib.sha256(invalid.read_bytes()).hexdigest())
    assert not (base/'unsafe').exists() and not (base/'escape.txt').exists()
    cases.append('archive path traversal rejected before writes')

proof={'result':'PASS','cases':cases,'real_powershell_extractor':True,'native_directory_lock':True,'empty_inherited_module_path':True,'production_installation_changed':False}
(ROOT/'.verification/bootstrap-extraction-tests.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(proof,ensure_ascii=False))
