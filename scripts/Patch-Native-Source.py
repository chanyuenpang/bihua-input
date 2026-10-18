"""Apply the small GPL Weasel 0.17.4 patch to the verified unpacked source."""
from pathlib import Path
import re
import difflib
import shutil

ROOT = Path(__file__).resolve().parent.parent
source = ROOT / '.verification/weasel-native/weasel-0.17.4'
changes = []
def change(name, function, encoding='utf-8-sig'):
    path = source / name
    before = path.read_text(encoding=encoding)
    after = function(before)
    if after != before:
        changes.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='a/'+name, tofile='b/'+name))
        path.write_text(after, encoding=encoding)

change('include/resource.h', lambda t: t.replace('#define ID_WEASELTRAY_LOGDIR            40016', '#define ID_WEASELTRAY_LOGDIR            40016\n#define ID_WEASELTRAY_BIHUA_SETTINGS    40017') if 'BIHUA_SETTINGS' not in t else t)
for name in ('WeaselServer/WeaselServer.rc', 'WeaselTSF/WeaselTSF.rc'):
    change(name, lambda t: re.sub(r'(\s*MENUITEM[^\n]*ID_WEASELTRAY_SETTINGS[^\n]*\n)', r'\1        MENUITEM "笔画设置 (&B)", ID_WEASELTRAY_BIHUA_SETTINGS\n', t.replace('afxres.h','winres.h')) if 'BIHUA_SETTINGS' not in t else t, 'utf-16')
change('WeaselServer/WeaselServerApp.cpp', lambda t: t.replace('std::filesystem::path dir = install_dir();', '''std::filesystem::path own_dir = install_dir();
  std::wstring stock_dir;
  RegGetStringValue(HKEY_CURRENT_USER, L"Software\\\\Rime\\\\Weasel", L"BihuaOriginalInstallDir", stock_dir);
  std::filesystem::path dir = stock_dir.empty() ? own_dir : std::filesystem::path(stock_dir);
  m_server.AddMenuHandler(ID_WEASELTRAY_BIHUA_SETTINGS,
    std::bind(execute, own_dir / L"BihuaSettingsLauncher.exe", std::wstring()));''') if 'BIHUA_SETTINGS' not in t else t)
change('WeaselServer/WeaselServer.cpp', lambda t: t.replace('  // command line option /q stops the running server', '''  if (!wcscmp(L"/bihua-settings", lpstrCmdLine)) {
    weasel::Client client;
    if (!client.Connect()) return 2;
    client.TrayCommand(ID_WEASELTRAY_BIHUA_SETTINGS);
    return 0;
  }
  // command line option /q stops the running server''') if '/bihua-settings' not in t else t)
change('WeaselServer/WeaselServer.cpp', lambda t: t.replace('  // command line option /q stops the running server', '''  if (!wcscmp(L"/bihua-engine-probe", lpstrCmdLine)) {
    weasel::Client client;
    if (!client.Connect()) return 2;
    client.StartSession();
    bool alive = client.Echo();
    client.FocusOut();
    client.EndSession();
    return alive ? 0 : 3;
  }
  // command line option /q stops the running server''') if '/bihua-engine-probe' not in t else t)
shutil.copy2(ROOT / 'native/BihuaFocusBoundary.h', source / 'include/BihuaFocusBoundary.h')
change('RimeWithWeasel/RimeWithWeasel.cpp', lambda t: t.replace('#include <rime_api.h>', '#include <rime_api.h>\n#include <BihuaFocusBoundary.h>').replace('  DLOG(INFO) << "Focus out: ipc_id = " << ipc_id;', '  DLOG(INFO) << "Focus out: ipc_id = " << ipc_id;\n  if (!m_disabled) BihuaNeutralFocusOut(rime_api, to_session_id(ipc_id));') if 'BihuaNeutralFocusOut' not in t else t)
if changes:
    (ROOT / 'native/weasel-0.17.4-bihua.patch').write_text(''.join(changes), encoding='utf-8')
print('Native source patch applied; original menus and IPC preserved.')
