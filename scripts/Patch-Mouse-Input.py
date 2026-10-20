"""Reproducible native mouse-mode delta over the verified 0.6.3 native source."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent.parent
SRC=ROOT/'.verification/weasel-native/weasel-0.17.4'
BASE=ROOT/'.verification/weasel-native/pre-mouse-063'
def edit(name, changes):
    path=SRC/name;backup=BASE/name
    if not backup.exists():backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,backup)
    text=backup.read_text(encoding='utf-8-sig')
    for old,new in changes:
        assert old in text,(name,old[:90])
        text=text.replace(old,new,1)
    path.write_text(text,encoding='utf-8-sig')

edit('WeaselIPC/PipeChannel.cpp',[
('''  if (pipe == INVALID_HANDLE_VALUE || !::ConnectNamedPipe(pipe, NULL)) {
    _ThrowLastError;
  }
  return pipe;''', '''  if (pipe == INVALID_HANDLE_VALUE) {
    _ThrowLastError;
  }
  if (!::ConnectNamedPipe(pipe, NULL)) {
    DWORD error = ::GetLastError();
    // A client can connect between CreateNamedPipe and ConnectNamedPipe.
    // ERROR_PIPE_CONNECTED is a valid connection; abandoning its local handle
    // leaves that client waiting forever for a server that never reads it.
    if (error != ERROR_PIPE_CONNECTED) {
      ::CloseHandle(pipe);
      throw error;
    }
  }
  return pipe;''')])

edit('include/WeaselIPC.h',[
('  WEASEL_IPC_LAST_COMMAND','  WEASEL_IPC_MOUSE_REGISTER,\n  WEASEL_IPC_MOUSE_TAKE,\n  WEASEL_IPC_MOUSE_EXECUTE,\n  WEASEL_IPC_MOUSE_FINISH,\n  WEASEL_IPC_MOUSE_PROFILE,\n  WEASEL_IPC_MOUSE_VIEW,\n  WEASEL_IPC_MOUSE_KEYBOARD_MODE,\n  WEASEL_IPC_MOUSE_MODE_TAKE,\n  WEASEL_IPC_MOUSE_SELECTION,\n  WEASEL_IPC_LAST_COMMAND'),
('  virtual void FocusIn(', '  virtual DWORD MouseCommand(WEASEL_IPC_COMMAND command, DWORD value, DWORD session, EatLine eat) { return 0; }\n  virtual void FocusIn('),
('  // 更新输入位置','  bool RegisterMouseTarget(HWND hwnd);\n  void SetMouseProfileActive(bool active);\n  bool MouseKeyboardMode(DWORD mode);\n  DWORD TakeMouseModeToggle();\n  bool MouseSelectedScalar(DWORD scalar);\n  DWORD MouseView(DWORD request);\n  DWORD TakeMouseAction();\n  bool ExecuteMouseAction(DWORD token);\n  void FinishMouseAction(DWORD token);\n  // 更新输入位置')])
edit('WeaselIPC/WeaselClientImpl.h',[
('  void UpdateInputPosition(', '  DWORD MouseCommand(WEASEL_IPC_COMMAND command, DWORD value);\n  void UpdateInputPosition(')])
edit('WeaselIPC/WeaselClientImpl.cpp',[
('void ClientImpl::UpdateInputPosition(','''DWORD ClientImpl::MouseCommand(WEASEL_IPC_COMMAND command, DWORD value) {
  return _Active() ? static_cast<DWORD>(_SendMessage(command,value,session_id)) : 0;
}

void ClientImpl::UpdateInputPosition('''),
('void Client::UpdateInputPosition(','''bool Client::RegisterMouseTarget(HWND hwnd) {
  return m_pImpl->MouseCommand(WEASEL_IPC_MOUSE_REGISTER,static_cast<DWORD>(reinterpret_cast<UINT_PTR>(hwnd)))!=0;
}
void Client::SetMouseProfileActive(bool active) {m_pImpl->MouseCommand(WEASEL_IPC_MOUSE_PROFILE,active?1:0);}
bool Client::MouseKeyboardMode(DWORD mode) {return m_pImpl->MouseCommand(WEASEL_IPC_MOUSE_KEYBOARD_MODE,mode)!=0;}
DWORD Client::TakeMouseModeToggle() {return m_pImpl->MouseCommand(WEASEL_IPC_MOUSE_MODE_TAKE,0);}
bool Client::MouseSelectedScalar(DWORD scalar) {return m_pImpl->MouseCommand(WEASEL_IPC_MOUSE_SELECTION,scalar)!=0;}
DWORD Client::MouseView(DWORD request) {return m_pImpl->MouseCommand(WEASEL_IPC_MOUSE_VIEW,request);}
DWORD Client::TakeMouseAction() {return m_pImpl->MouseCommand(WEASEL_IPC_MOUSE_TAKE,0);}
bool Client::ExecuteMouseAction(DWORD token) {return m_pImpl->MouseCommand(WEASEL_IPC_MOUSE_EXECUTE,token)!=0;}
void Client::FinishMouseAction(DWORD token) {m_pImpl->MouseCommand(WEASEL_IPC_MOUSE_FINISH,token);}

void Client::UpdateInputPosition(''')])
edit('include/WeaselIPCData.h',[
('struct Config {','struct Config {\n  bool mouse_selection_enabled = false;\n  bool mouse_panel_enabled = false;'),
('void reset() { inline_preedit = false; }','void reset() { inline_preedit = false; mouse_panel_enabled = false; mouse_selection_enabled = false; }')])
edit('WeaselIPC/Configurator.cpp',[
('!m_pTarget->p_context','!m_pTarget->p_config'),
('  if (key[1] == L"inline_preedit") {','  if (key[1] == L"mouse_selection_enabled") m_pTarget->p_config->mouse_selection_enabled = bool_value;\n  if (key[1] == L"mouse_panel_enabled") m_pTarget->p_config->mouse_panel_enabled = bool_value;\n  if (key[1] == L"inline_preedit") {')])
edit('WeaselIPCServer/WeaselServerImpl.h',[
('  DWORD OnChangePage(', '  DWORD OnMouseCommand(WEASEL_IPC_COMMAND uMsg, DWORD wParam, DWORD lParam);\n  DWORD OnChangePage('),
('  BOOL m_darkMode;','  BOOL m_darkMode;\n  DWORD m_request_pid = 0;\n  PipeChannel<DWORD,PipeMessage>* m_request_channel = nullptr;\n  std::map<DWORD,DWORD> m_session_owners;')])
edit('WeaselIPCServer/WeaselServerImpl.cpp',[
('class PipeServer : public PipeChannel<DWORD, PipeMessage> {', '''// Connection buffers must never be shared between concurrent pipe threads.
class ServerPipeConnection : public PipeChannel<DWORD,PipeMessage> {
 public:
  ServerPipeConnection():PipeChannel(GetPipeName()){}
  void Receive(HANDLE pipe,PipeMessage& message){_Receive(pipe,&message,sizeof(message));}
  void Reply(HANDLE pipe,DWORD result){
    *reinterpret_cast<DWORD*>(buffer.get())=result;
    DWORD size=static_cast<DWORD>(has_body?buff_size:sizeof(result)),written=0;
    // Write after the Rime API lock is released. Do not flush a named pipe:
    // FlushFileBuffers waits for its peer and can freeze every input client.
    BOOL ok=WriteFile(pipe,buffer.get(),size,&written,nullptr);
    DWORD error=ok?ERROR_WRITE_FAULT:GetLastError();
    ClearBufferStream();
    if(!ok||written!=size)throw error;
  }
};
class PipeServer : public PipeChannel<DWORD, PipeMessage> {'''),
('std::function<void(PipeMessage, Respond)>','std::function<void(PipeMessage, DWORD, ServerPipeConnection&, Respond)>'),
('auto listener = [this](PipeMessage msg, PipeServer::Respond resp) -> void {\n    std::lock_guard guard(g_api_mutex);\n    HandlePipeMessage(msg, resp);\n  };', '''auto listener = [this](PipeMessage msg,DWORD pid,ServerPipeConnection& connection,PipeServer::Respond resp) -> void {
    DWORD result=0;
    {
      std::lock_guard guard(g_api_mutex);
      m_request_pid=pid;m_request_channel=&connection;
      HandlePipeMessage(msg,[&](DWORD value){result=value;});
      m_request_channel=nullptr;
    }
    resp(result);
  };'''),
('reinterpret_cast<LPWSTR>(channel->ReceiveBuffer())','reinterpret_cast<LPWSTR>(m_request_channel->ReceiveBuffer())'),
('#define MAP_PIPE_MSG_HANDLE', '''DWORD ServerImpl::OnMouseCommand(WEASEL_IPC_COMMAND command,DWORD value,DWORD session) {
  auto owner=m_session_owners.find(session);
  if(!m_pRequestHandler||!m_request_pid||owner==m_session_owners.end()||owner->second!=m_request_pid)return 0;
  if(command==WEASEL_IPC_MOUSE_REGISTER&&value){
    DWORD pid=0;GetWindowThreadProcessId(reinterpret_cast<HWND>(static_cast<UINT_PTR>(value)),&pid);
    if(pid!=m_request_pid)return 0;
  }
  return m_pRequestHandler->MouseCommand(command,value,session,[this](std::wstring& line){*m_request_channel<<line;return true;});
}

#define MAP_PIPE_MSG_HANDLE'''),
('  DWORD result;','  DWORD result = 0;'),
('  PIPE_MSG_HANDLE(WEASEL_IPC_ECHO, OnEcho)','  PIPE_MSG_HANDLE(WEASEL_IPC_MOUSE_REGISTER, OnMouseCommand)\n  PIPE_MSG_HANDLE(WEASEL_IPC_MOUSE_TAKE, OnMouseCommand)\n  PIPE_MSG_HANDLE(WEASEL_IPC_MOUSE_EXECUTE, OnMouseCommand)\n  PIPE_MSG_HANDLE(WEASEL_IPC_MOUSE_FINISH, OnMouseCommand)\n  PIPE_MSG_HANDLE(WEASEL_IPC_MOUSE_PROFILE, OnMouseCommand)\n  PIPE_MSG_HANDLE(WEASEL_IPC_MOUSE_VIEW, OnMouseCommand)\n  PIPE_MSG_HANDLE(WEASEL_IPC_MOUSE_KEYBOARD_MODE, OnMouseCommand)\n  PIPE_MSG_HANDLE(WEASEL_IPC_MOUSE_MODE_TAKE, OnMouseCommand)\n  PIPE_MSG_HANDLE(WEASEL_IPC_MOUSE_SELECTION, OnMouseCommand)\n  PIPE_MSG_HANDLE(WEASEL_IPC_ECHO, OnEcho)'),
('  END_MAP_PIPE_MSG_HANDLE(result);\n\n  resp(result);','  END_MAP_PIPE_MSG_HANDLE(result);\n  if(pipe_msg.Msg==WEASEL_IPC_START_SESSION&&result)m_session_owners[result]=m_request_pid;\n  if(pipe_msg.Msg==WEASEL_IPC_END_SESSION)m_session_owners.erase(pipe_msg.lParam);\n  resp(result);'),
('  try {\n    for (;;) {\n      Res msg;', '  try {\n    ServerPipeConnection connection;\n    ULONG peer_pid=0;GetNamedPipeClientProcessId(pipe,&peer_pid);\n    for (;;) {\n      Res msg;'),
('      _Receive(pipe, &msg, sizeof(msg));','      connection.Receive(pipe,msg);'),
('        _Send(pipe, rejected);','        connection.Reply(pipe,rejected);'),
('      handler(msg, [this, pipe](Msg resp) { _Send(pipe, resp); });','      handler(msg,peer_pid,connection,[&connection,pipe](Msg result){connection.Reply(pipe,result);});')])
ipc=SRC/'WeaselIPCServer/WeaselServerImpl.cpp'
ipc.write_text(ipc.read_text(encoding='utf-8-sig').replace('*channel << msg','*m_request_channel << msg'),encoding='utf-8-sig')
edit('include/RimeWithWeasel.h',[
('#include <rime_api.h>','#include <rime_api.h>\n#include <BihuaMouseState.h>\n#include <BihuaMousePanel.h>\n#include <BihuaMouseView.h>\n#include <BihuaStrokeInfo.h>\n#include <BihuaNumLock.h>\n#include <mutex>\n#include <atomic>'),
('  virtual void FocusIn(', '  virtual DWORD MouseCommand(WEASEL_IPC_COMMAND command,DWORD value,DWORD session,EatLine eat);\n  virtual void FocusIn('),
('  void _Setup();','''  void _Setup();
  void _QueueMouseAction(int action,int index,DWORD displayed_generation,uint64_t revision,uint64_t view);
  void _MouseDisplayed(DWORD generation,uint64_t revision,int first,int count);
  void _BeforeMouseMutation(DWORD session);
  void _UpdateNumLock();
  BihuaNumLockGuard m_numlock;
  void _UpdateMouse(DWORD session);
  bool _MouseHeartbeat();
  bool _MouseTargetValid();
  bool _MouseProfileVisible();
  DWORD _MouseProfileSession();
  std::unique_ptr<BihuaMousePanel> m_mouse_panel;
  std::recursive_mutex m_mouse_mutex;
  std::atomic<bool> m_mouse_enabled{false};
  bool m_mouse_ascii=false;
  BihuaMouseState m_mouse_state;
  BihuaMouseView m_mouse_view;
  BihuaStrokeInfo m_mouse_strokes;
  bool m_mouse_info=true,m_mouse_arrows=true,m_mouse_copy=true,m_mouse_selection=false;
  uint64_t m_mouse_pending_view=0;
  DWORD m_mouse_mode_session=0,m_mouse_mode_serial=0,m_mouse_mode_token=0,m_mouse_mode_owner=0;
  ULONGLONG m_mouse_mode_at=0;
  std::vector<std::wstring> m_mouse_candidates;
  int m_mouse_page_size=9,m_mouse_base=0;
  bool m_mouse_more=false;
  struct MouseExposure {DWORD session=0,generation=0;uint64_t revision=0;int first=0,count=0;};
  MouseExposure m_mouse_exposure;
  std::map<DWORD,HWND> m_mouse_targets;
  struct MouseProfile {DWORD pid=0,thread=0;bool active=false;int mode=-1;};
  std::map<DWORD,MouseProfile> m_mouse_profiles;''')])
edit('RimeWithWeasel/RimeWithWeasel.cpp',[
('void RimeWithWeaselHandler::Initialize() {','void RimeWithWeaselHandler::Initialize() {\n  std::lock_guard<std::recursive_mutex> mouse_lock(m_mouse_mutex);'),
('  _Setup();\n}', '''  _Setup();
  wchar_t executable[32768]{};GetModuleFileNameW(nullptr,executable,32768);
  m_mouse_strokes.Load(std::filesystem::path(executable).parent_path()/L"data");
  m_mouse_panel=std::make_unique<BihuaMousePanel>();
  m_mouse_panel->clicked=[this](int action,int index,DWORD generation,uint64_t revision,uint64_t view){_QueueMouseAction(action,index,generation,revision,view);};
  m_mouse_panel->displayed=[this](DWORD generation,uint64_t revision,int first,int count){_MouseDisplayed(generation,revision,first,count);};
  m_mouse_panel->target_valid=[this](){return _MouseHeartbeat();};
  m_mouse_panel->ConfigurePersonal(WeaselUserDataPath(),std::filesystem::path(executable).parent_path(),m_mouse_copy,m_mouse_selection);
  m_mouse_panel->Create();
}'''),
('    _LoadAppOptions(&config, m_app_options);', '''    Bool mouse_enabled=false;
    rime_api->config_get_bool(&config,"bihua_mouse/enabled",&mouse_enabled);
    m_mouse_enabled=!!mouse_enabled;
    Bool info=true,arrows=true;
    rime_api->config_get_bool(&config,"bihua_mouse/stroke_info",&info);
    rime_api->config_get_bool(&config,"bihua_mouse/arrow_navigation",&arrows);
    m_mouse_info=!!info;m_mouse_arrows=!!arrows;
    Bool copy=true,selected=false;
    rime_api->config_get_bool(&config,"bihua_mouse/copy_stroke",&copy);
    rime_api->config_get_bool(&config,"bihua_mouse/selection_stroke",&selected);
    m_mouse_copy=!!copy;m_mouse_selection=!!selected;
    if(m_mouse_panel){
      wchar_t program[32768]{};GetModuleFileNameW(nullptr,program,32768);
      m_mouse_panel->ConfigurePersonal(WeaselUserDataPath(),std::filesystem::path(program).parent_path(),m_mouse_copy,m_mouse_selection);
      RimeConfig key_config={NULL};
      BihuaPersonalKeyMap keys;
      if(rime_api->schema_open("bihua_mvp",&key_config)){
        keys=BihuaPersonalKeyMap::Read([&](const std::string& path){
          char value[64]{};return rime_api->config_get_string(&key_config,path.c_str(),value,sizeof(value))?std::string(value):std::string();
        });
        rime_api->config_close(&key_config);
      }
      m_mouse_panel->ConfigurePersonalKeys(keys);
    }
    _LoadAppOptions(&config, m_app_options);'''),
('  m_last_schema_id.clear();\n}', '  m_last_schema_id.clear();\n  _UpdateMouse(0);\n}'),
('void RimeWithWeaselHandler::Finalize() {','''void RimeWithWeaselHandler::Finalize() {
  std::lock_guard<std::recursive_mutex> mouse_lock(m_mouse_mutex);
  {std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);m_mouse_state.Focus(0);m_mouse_targets.clear();m_mouse_profiles.clear();}
  _UpdateMouse(0);'''),
('DWORD RimeWithWeaselHandler::RemoveSession(WeaselSessionId ipc_id) {','''DWORD RimeWithWeaselHandler::RemoveSession(WeaselSessionId ipc_id) {
  {std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);m_mouse_state.Blur(ipc_id);m_mouse_targets.erase(ipc_id);m_mouse_profiles.erase(ipc_id);}
  _UpdateMouse(0);'''),
('  _UpdateUI(ipc_id);\n  m_active_session = ipc_id;\n}\n\nvoid RimeWithWeaselHandler::FocusOut', '''  {std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);
    auto target=m_mouse_targets.find(ipc_id);
    if(target!=m_mouse_targets.end()){
      DWORD pid=0,front=0;GetWindowThreadProcessId(target->second,&pid);GetWindowThreadProcessId(GetForegroundWindow(),&front);
      if(pid&&pid==front&&m_mouse_state.session!=ipc_id)m_mouse_state.Focus(ipc_id);
    }
  }
  _UpdateUI(ipc_id);
  m_active_session = ipc_id;
}

void RimeWithWeaselHandler::FocusOut'''),
('  m_active_session = 0;\n}\n\nvoid RimeWithWeaselHandler::UpdateInputPosition', '''  if(m_active_session==ipc_id)m_active_session = 0;
  {std::lock_guard<std::recursive_mutex> lock(m_mouse_mutex);m_mouse_state.Blur(ipc_id);}
  _UpdateMouse(0);
}

void RimeWithWeaselHandler::UpdateInputPosition'''),
('void RimeWithWeaselHandler::UpdateColorTheme(BOOL darkMode) {','void RimeWithWeaselHandler::UpdateColorTheme(BOOL darkMode) {\n  std::lock_guard<std::recursive_mutex> mouse_lock(m_mouse_mutex);'),
('void RimeWithWeaselHandler::_UpdateUI(WeaselSessionId ipc_id) {','''void RimeWithWeaselHandler::_UpdateUI(WeaselSessionId ipc_id) {
  _UpdateMouse(ipc_id);
  if(m_mouse_enabled){if(m_ui)m_ui->Hide();return;}'''),
('  // configuration information','  // configuration information\n  messages.push_back(std::string("config.mouse_selection_enabled=")+std::to_string(m_mouse_selection?1:0)+\'\\n\');\n  messages.push_back(std::string("config.mouse_panel_enabled=")+std::to_string(m_mouse_enabled?1:0)+\'\\n\');')])

# Keep the backend delta as ordinary reviewable C++, then include it in the
# generated implementation where RimeWithWeaselHandler and u8tow are available.
shutil.copy2(ROOT/'native/BihuaMouseBackend.h',SRC/'include/BihuaMouseBackend.h')
path=SRC/'RimeWithWeasel/RimeWithWeasel.cpp'
text=path.read_text(encoding='utf-8-sig')
for old,new in [
 ('  Bool handled = rime_api->process_key(session_id, keyEvent.keycode,','  _BeforeMouseMutation(ipc_id);\n  Bool handled = rime_api->process_key(session_id, keyEvent.keycode,'),
 ('  rime_api->commit_composition(to_session_id(ipc_id));','  _BeforeMouseMutation(ipc_id);\n  rime_api->commit_composition(to_session_id(ipc_id));'),
 ('  rime_api->clear_composition(to_session_id(ipc_id));','  _BeforeMouseMutation(ipc_id);\n  rime_api->clear_composition(to_session_id(ipc_id));'),
 ('  rime_api->select_candidate_on_current_page(to_session_id(ipc_id), index);','  _BeforeMouseMutation(ipc_id);\n  rime_api->select_candidate_on_current_page(to_session_id(ipc_id), index);'),
 ('  bool res = rime_api->highlight_candidate_on_current_page(','  _BeforeMouseMutation(ipc_id);\n  bool res = rime_api->highlight_candidate_on_current_page('),
 ('  bool res = rime_api->change_page(to_session_id(ipc_id), backward);','  _BeforeMouseMutation(ipc_id);\n  bool res = rime_api->change_page(to_session_id(ipc_id), backward);'),
 ('  // from no-session client, not actual typing session','  _BeforeMouseMutation(ipc_id ? ipc_id : m_active_session);\n  // from no-session client, not actual typing session'),
]:
    assert old in text,old
    text=text.replace(old,new,1)
path.write_text(text+'\n#include <BihuaMouseBackend.h>\n',encoding='utf-8-sig')

edit('WeaselTSF/WeaselTSF.h',[
('#include <WeaselIPC.h>','#include <WeaselIPC.h>\n#include <BihuaKeyboardRoute.h>'),
('  /* UI */','''  bool _RouteMouseKey(WPARAM key,LPARAM info,BOOL* eaten,int phase);
  void _InitMouseTarget();
  void _RefreshMouseFocus();
  void _SyncMouseMode();
  void _WakeMouseAction();
  void _WakeMouseMode();
  void _ObserveMouseSelection();
  void _FinishMouseSelection(){_mouseSelectionPending=false;}
  HRESULT _ReadMouseSelection(com_ptr<ITfContext> context,TfEditCookie ec);
  void _FinishMouseAction(DWORD token);
  HRESULT _RunMouseAction(DWORD token,com_ptr<ITfContext> context,TfEditCookie ec);
  com_ptr<ITfContext> _MouseContext();
  bool MousePanelEnabled() const {return _mousePanelEnabled;}
  /* UI */'''),
('  BOOL _async_edit = false;','''  HWND _mouseWindow=nullptr;
  bool _mouseOwnActive=true,_mousePanelEnabled=false,_endingMouseComposition=false;
  com_ptr<ITfContext> _mouseContext;
  BihuaKeyboardRoute _mouseKeyboard;
  bool _mouseModeDirty=true,_mouseSelectionEnabled=false,_mouseSelectionPending=false;
  DWORD _mouseSelectedScalar=0;
  bool _mouseViewKeys[256]{};
  BOOL _async_edit = false;''')])
edit('WeaselTSF/WeaselTSF.cpp',[
('  _activateFlags = dwFlags;','  _activateFlags = dwFlags;\n  _mouseOwnActive=true;'),
('  m_client.EndSession();','  _mouseOwnActive=false;\n  m_client.SetMouseProfileActive(false);\n  m_client.RegisterMouseTarget(nullptr);\n  if(_mouseWindow){DestroyWindow(_mouseWindow);_mouseWindow=nullptr;}\n  _mouseContext=nullptr;\n  m_client.EndSession();'),
('  _EnsureServerConnected();','  _InitMouseTarget();\n  _EnsureServerConnected();\n  _RefreshMouseFocus();'),
('STDMETHODIMP WeaselTSF::OnKillThreadFocus() {','STDMETHODIMP WeaselTSF::OnKillThreadFocus() {\n  _mouseKeyboard.CancelGesture();\n  m_client.FocusOut();\n  _mouseContext=nullptr;'),
('  if (isActivated) {','  _mouseOwnActive=!!isActivated;\n  if(!isActivated)_mouseKeyboard.Reset();\n  _mouseModeDirty=true;\n  m_client.SetMouseProfileActive(_mouseOwnActive);\n  if (isActivated) {\n    _RefreshMouseFocus();'),
('  } else {\n    _DeleteCandidateList();','  } else {\n    m_client.FocusOut();\n    _mouseContext=nullptr;\n    _DeleteCandidateList();'),
('  weasel::ResponseParser parser(NULL, NULL, &_status, NULL, &_cand->style());\n  bool ok = m_client.GetResponseData(std::ref(parser));','  weasel::Config config;\n  weasel::ResponseParser parser(NULL, NULL, &_status, &config, &_cand->style());\n  bool ok = m_client.GetResponseData(std::ref(parser));\n  _mousePanelEnabled=config.mouse_panel_enabled;\n  _mouseSelectionEnabled=config.mouse_selection_enabled;\n  m_client.RegisterMouseTarget(_mouseWindow);\n  m_client.SetMouseProfileActive(_mouseOwnActive);\n  _mouseContext=nullptr;\n  _mouseKeyboard.Reset();\n  _mouseModeDirty=true;\n  _RefreshMouseFocus();')])
with (SRC/'WeaselTSF/WeaselTSF.cpp').open('a',encoding='utf-8') as file:file.write('\n#include "BihuaMouseTSF.h"\n')
edit('WeaselTSF/KeyEventSink.cpp',[
('  weasel::KeyEvent ke;','  _RefreshMouseFocus();\n  weasel::KeyEvent ke;'),
('  if (fForeground)\n    m_client.FocusIn();','  if (fForeground)\n    _RefreshMouseFocus();'),
*[(f'''STDAPI WeaselTSF::{name}(ITfContext* pContext,
{indent}WPARAM wParam,
{indent}LPARAM lParam,
{indent}BOOL* pfEaten) {{''',f'''STDAPI WeaselTSF::{name}(ITfContext* pContext,
{indent}WPARAM wParam,
{indent}LPARAM lParam,
{indent}BOOL* pfEaten) {{
  if (_RouteMouseKey(wParam,lParam,pfEaten,{phase})) return S_OK;
  // Mouse mode leaves Return entirely to the application. In particular, do
  // not process a Rime key or run an edit session for either press or release.
  // Both physical Enter keys have VK_RETURN; modifiers remain application-owned.
  if (_mousePanelEnabled && wParam == VK_RETURN) {{
    *pfEaten = FALSE;
    return S_OK;
  }}''') for name,indent,phase in [('OnTestKeyDown','                                ',0),
                          ('OnKeyDown','                            ',1),
                          ('OnTestKeyUp','                              ',2),
                          ('OnKeyUp','                          ',3)]]])
edit('WeaselTSF/ThreadMgrEventSink.cpp',[
('  _InitTextEditSink(pDocMgrFocus);','  _InitTextEditSink(pDocMgrFocus);\n  _RefreshMouseFocus();')])
edit('WeaselTSF/EditSession.cpp',[
('  _UpdateLanguageBar(_status);','  _mousePanelEnabled=config.mouse_panel_enabled;\n  _mouseSelectionEnabled=config.mouse_selection_enabled;\n  _UpdateLanguageBar(_status);'),
('if (_status.composing && !_IsComposing()) {',
 'if (_status.composing && !_IsComposing() && !_mousePanelEnabled) {'),
('} else if (!_status.composing && _IsComposing()) {',
 '} else if ((!_status.composing || _mousePanelEnabled) && _IsComposing()) {')])
edit('WeaselTSF/Composition.cpp',[
('  // NOTE:\n', '  if(_endingMouseComposition)return S_OK;\n  // NOTE:\n')])
edit('WeaselTSF/CandidateList.cpp',[
('void CCandidateList::UpdateUI(const Context& ctx, const Status& status) {','void CCandidateList::UpdateUI(const Context& ctx, const Status& status) {\n  if(_tsf->MousePanelEnabled()){Show(FALSE);return;}'),
('void CCandidateList::StartUI() {','void CCandidateList::StartUI() {\n  if(_tsf->MousePanelEnabled())return;'),
('void WeaselTSF::_ShowUI() {','void WeaselTSF::_ShowUI() {\n  if(_mousePanelEnabled)return;')])
for name in ('BihuaMouseState.h','BihuaMousePanel.h','BihuaMouseView.h','BihuaStrokeInfo.h','BihuaKeyboardRoute.h','BihuaPersonalRecorder.h','BihuaPersonalKeys.h','BihuaNumLock.h'):shutil.copy2(ROOT/'native'/name,SRC/'include'/name)
shutil.copy2(ROOT/'native/BihuaMouseTSF.h',SRC/'WeaselTSF/BihuaMouseTSF.h')
print('Native mouse server/IPC patch applied')
