"""Minimal native 0.5.1 repair: one settings action, pinned schema and no stock takeover."""
from pathlib import Path
import re
import shutil

root=Path(__file__).resolve().parent.parent
source=root/'.verification/weasel-native/weasel-0.17.4'
def edit(name,operation,encoding='utf-8-sig'):
    path=source/name;text=path.read_text(encoding=encoding)
    changed=operation(text)
    if changed!=text:path.write_text(changed,encoding=encoding)

edit('include/resource.h',lambda t:t+'\n#define ID_BIHUA_ENABLE 40018\n' if 'ID_BIHUA_ENABLE' not in t else t)
for name in ('WeaselServer/WeaselServer.rc','WeaselTSF/WeaselTSF.rc'):
    edit(name,lambda t:re.sub(r'(?m)^IDR_MENU_POPUP(?:_HANT|_HANS)? MENU\s*\nBEGIN\n.*?^END',
        lambda m:m.group(0).split(' MENU')[0]+''' MENU
BEGIN
    POPUP "笔画输入法"
    BEGIN
        MENUITEM "笔画设置", ID_WEASELTRAY_BIHUA_SETTINGS
    END
END''',t,flags=re.S), 'utf-16')
edit('include/RimeWithWeasel.h',lambda t:t.replace('  virtual void Initialize();','  bool ActivateBihua();\n  virtual void Initialize();') if 'ActivateBihua' not in t else t)
edit('RimeWithWeasel/RimeWithWeasel.cpp',lambda t:t.replace('  if (m_global_ascii_mode) {\n    for (const auto& pair : m_session_status_map)',
    '''  if (!session_id || !rime_api->select_schema(session_id, "bihua_mvp")) {
    if (session_id) rime_api->destroy_session(session_id);
    return 0;
  }
  if (m_global_ascii_mode) {
    for (const auto& pair : m_session_status_map)''',1) if 'if (!session_id || !rime_api->select_schema' not in t else t)
edit('RimeWithWeasel/RimeWithWeasel.cpp',lambda t:t+'''
bool RimeWithWeaselHandler::ActivateBihua() {
  if (m_disabled) return false;
  RimeSessionId session = m_active_session ? to_session_id(m_active_session) : 0;
  bool temporary = !session || !rime_api->find_session(session);
  if (temporary) session = rime_api->create_session();
  bool selected = session && rime_api->select_schema(session, "bihua_mvp");
  if (selected) {
    rime_api->set_option(session, "ascii_mode", false);
    rime_api->set_option(session, "simplification", true);
    if (!temporary) {
      _LoadSchemaSpecificSettings(m_active_session, "bihua_mvp");
      _UpdateUI(m_active_session);
    }
  }
  if (temporary && session) rime_api->destroy_session(session);
  return selected;
}
''' if 'bool RimeWithWeaselHandler::ActivateBihua()' not in t else t)
edit('WeaselServer/WeaselServerApp.cpp',lambda t:t.replace('  std::wstring stock_dir;', '  m_server.AddMenuHandler(ID_BIHUA_ENABLE, [this] { return m_handler->ActivateBihua(); });\n  std::wstring stock_dir;').replace('std::filesystem::path dir = stock_dir.empty() ? own_dir : std::filesystem::path(stock_dir);','std::filesystem::path dir = own_dir;') if 'ID_BIHUA_ENABLE' not in t else t)
edit('WeaselServer/WeaselServer.cpp',lambda t:t.replace('#include <memory>','#include <memory>\n#include <fstream>') if '#include <fstream>' not in t else t)
edit('WeaselServer/WeaselServer.cpp',lambda t:t.replace('  if (!wcscmp(L"/bihua-settings", lpstrCmdLine)) {','''  if (!wcscmp(L"/bihua-enable", lpstrCmdLine)) {
    weasel::Client client;
    if (!client.Connect()) return 2;
    client.TrayCommand(ID_BIHUA_ENABLE);
    return 0;
  }
  if (!wcscmp(L"/bihua-reload", lpstrCmdLine)) {
    weasel::Client client;
    if (!client.Connect()) return 2;
    client.StartMaintenance(); client.EndMaintenance();
    return 0;
  }
  if (!wcscmp(L"/bihua-settings", lpstrCmdLine)) {''') if '/bihua-enable' not in t else t)
edit('WeaselServer/WeaselServer.cpp',lambda t:t.replace('    client.StartSession();\n    bool alive = client.Echo();','''    client.StartSession();
    std::string status_lines;
    client.GetResponseData([&](LPWSTR buffer, DWORD length) {
      std::wstring response(buffer);
      size_t position = 0;
      while (position < response.size()) {
        auto end = response.find(L'\\n', position);
        auto line = response.substr(position, end == std::wstring::npos ? end : end-position);
        if (line.find(L"status.") == 0) status_lines += wtou8(line) + "\\n";
        if (end == std::wstring::npos) break;
        position = end + 1;
      }
      return true;
    });
    std::ofstream proof(WeaselServerApp::install_dir() / L"bihua-engine-session.txt");
    proof << status_lines;
    bool alive = client.Echo();''').replace('    return alive ? 0 : 3;', '    return alive && status_lines.find("status.schema_id=bihua_mvp") != std::string::npos ? 0 : 3;') if 'status_lines;' not in t else t)
shutil.copy2(root/'native/BihuaServerIdentity.h',source/'include/BihuaServerIdentity.h')
edit('WeaselIPCServer/WeaselServerImpl.cpp',lambda t:t.replace('#include <Windows.h>','#include <Windows.h>\n#include <BihuaServerIdentity.h>').replace('      _Receive(pipe, &msg, sizeof(msg));','''      _Receive(pipe, &msg, sizeof(msg));
      if (msg.Msg == WEASEL_IPC_SHUTDOWN_SERVER && BihuaIsOtherServerCaller(pipe)) {
        DWORD rejected = 0;
        _Send(pipe, rejected);
        continue;
      }''') if 'BihuaIsOtherServerCaller' not in t else t)
print('Patched one settings menu action, schema activation/pinning, real session status and stock-takeover guard.')
