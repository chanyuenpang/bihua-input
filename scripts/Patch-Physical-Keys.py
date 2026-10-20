"""Reproducible versioned physical-event delta after Patch-Mouse-Input.py."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parent.parent
SRC=ROOT/'.verification/weasel-native/weasel-0.17.4'
BASE=ROOT/'.verification/weasel-native/pre-physical-0630'
MARKER='// Bihua physical event v1'
def edit(name,pairs):
    path=SRC/name;backup=BASE/name
    text=path.read_text(encoding='utf-8-sig')
    if MARKER in text:
        text=backup.read_text(encoding='utf-8-sig')
    else:
        backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,backup)
    for old,new in pairs:
        assert old in text,(name,old[:100]);text=text.replace(old,new,1)
    path.write_text(MARKER+'\n'+text,encoding='utf-8-sig')
definition=SRC/'WeaselTSF/WeaselTSF.def'
if 'BihuaGetPhysicalKeyProtocolVersion' not in definition.read_text(encoding='utf-8-sig'):
    with definition.open('a',encoding='utf-8') as f:f.write('\n\tBihuaGetPhysicalKeyProtocolVersion\n')
edit('WeaselTSF/DllMain.cpp',[
('BOOL WINAPI DllMain(', 'extern "C" UINT __cdecl BihuaGetPhysicalKeyProtocolVersion(){return 1;}\n\nBOOL WINAPI DllMain(')])
edit('include/WeaselIPC.h',[
('#include <KeyEvent.h>','#include <KeyEvent.h>\n#include <BihuaPhysicalKey.h>'),
('  WEASEL_IPC_LAST_COMMAND','  WEASEL_IPC_PHYSICAL_CAPABILITY,\n  WEASEL_IPC_PHYSICAL_KEY,\n  WEASEL_IPC_PHYSICAL_QUERY,\n  WEASEL_IPC_LAST_COMMAND'),
('  virtual void CommitComposition(', '  virtual DWORD PhysicalKeyEvent(const BihuaPhysicalEventV1& event,DWORD session,EatLine eat,bool query){return 0;}\n  virtual void CommitComposition('),
('  bool CommitComposition();','  bool ProcessPhysicalKeyEvent(UINT vk,LPARAM info,const KeyEvent& legacy);\n  bool IsPhysicalKeyBound(UINT vk,LPARAM info);\n  bool CommitComposition();')])
edit('include/PipeChannel.h',[
('  /* Write data to buffer */','''  size_t ReceivedBodyBytes()const{return received_body_bytes;}
  const char* ReceivedPayload()const{return buffer.get();}
  void WritePayload(const void* data,size_t size){
    if(!data||size>buff_size-_MsgSize)throw DWORD(ERROR_INVALID_DATA);
    ClearBufferStream();memset(buffer.get()+_MsgSize,0,buff_size-_MsgSize);
    memcpy(buffer.get()+_MsgSize,data,size);has_body=true;
  }
  /* Write data to buffer */'''),
('  bool has_body;', '  size_t received_body_bytes=0;\n  bool has_body;')])
edit('WeaselIPC/PipeChannel.cpp',[
('  DWORD lread;\n  BOOL success = ::ReadFile(pipe, msg, rec_len, &lread, NULL);','  received_body_bytes=0;bool body=false;\n  DWORD lread;\n  BOOL success = ::ReadFile(pipe, msg, rec_len, &lread, NULL);\n  if(lread!=rec_len)throw DWORD(ERROR_INVALID_DATA);'),
('    memset(buffer.get(), 0, buff_size);','    body=true;\n    memset(buffer.get(), 0, buff_size);'),
('  has_body = false;\n}\n\nHANDLE PipeChannelBase::_ConnectServerPipe', '  if(!success)throw DWORD(ERROR_READ_FAULT);\n  received_body_bytes=body?lread:0;\n  has_body = false;\n}\n\nHANDLE PipeChannelBase::_ConnectServerPipe')])
edit('WeaselIPC/WeaselClientImpl.h',[
('  bool CommitComposition();','  bool ProcessPhysicalKeyEvent(UINT vk,LPARAM info,const KeyEvent& legacy);\n  bool IsPhysicalKeyBound(UINT vk,LPARAM info);\n  DWORD PhysicalRequest(UINT vk,LPARAM info,const KeyEvent& legacy,bool query);\n  bool CommitComposition();'),
('  UINT session_id;','  int physical_capability=-1;\n  UINT session_id;')])
edit('WeaselIPC/WeaselClientImpl.cpp',[
('  session_id = ret;','  session_id = ret;\n  physical_capability=-1;'),
('bool ClientImpl::CommitComposition() {','''DWORD ClientImpl::PhysicalRequest(UINT vk,LPARAM raw,const KeyEvent& legacy,bool query){
  if(!_Active())return 0;
  if(physical_capability<0)physical_capability=_SendMessage(WEASEL_IPC_PHYSICAL_CAPABILITY,0,session_id)==1?1:0;
  if(!physical_capability)return query?0:(legacy.keycode?ProcessKeyEvent(legacy):0);
  KeyInfo info(raw);BihuaPhysicalEventV1 event;event.vk=vk;event.scan=info.scanCode;
  event.flags=(info.isExtended?1:0)|(info.isKeyUp?2:0)|(info.prevKeyState?4:0);event.repeat=info.repeatCount;event.rime=legacy;
  if(!event.Valid())return 0;
  channel.WritePayload(&event,sizeof(event));
  return static_cast<DWORD>(_SendMessage(query?WEASEL_IPC_PHYSICAL_QUERY:WEASEL_IPC_PHYSICAL_KEY,sizeof(event),session_id));
}
bool ClientImpl::ProcessPhysicalKeyEvent(UINT vk,LPARAM info,const KeyEvent& legacy){return PhysicalRequest(vk,info,legacy,false)!=0;}
bool ClientImpl::IsPhysicalKeyBound(UINT vk,LPARAM info){return PhysicalRequest(vk,info,KeyEvent(),true)!=0;}
bool ClientImpl::CommitComposition() {'''),
('bool Client::CommitComposition() {','''bool Client::ProcessPhysicalKeyEvent(UINT vk,LPARAM info,const KeyEvent& legacy){return m_pImpl->ProcessPhysicalKeyEvent(vk,info,legacy);}
bool Client::IsPhysicalKeyBound(UINT vk,LPARAM info){return m_pImpl->IsPhysicalKeyBound(vk,info);}
bool Client::CommitComposition() {''')])
edit('WeaselIPCServer/WeaselServerImpl.h',[
('  DWORD OnKeyEvent(', '  DWORD OnPhysicalKey(WEASEL_IPC_COMMAND command,DWORD size,DWORD session);\n  DWORD OnKeyEvent(')])
edit('WeaselIPCServer/WeaselServerImpl.cpp',[
('#define MAP_PIPE_MSG_HANDLE','''DWORD ServerImpl::OnPhysicalKey(WEASEL_IPC_COMMAND command,DWORD size,DWORD session){
  auto owner=m_session_owners.find(session);
  if(!m_pRequestHandler||!m_request_pid||owner==m_session_owners.end()||owner->second!=m_request_pid)return 0;
  if(command==WEASEL_IPC_PHYSICAL_CAPABILITY)return 1;
  if(size!=sizeof(BihuaPhysicalEventV1)||m_request_channel->ReceivedBodyBytes()<sizeof(BihuaPhysicalEventV1)){
    OutputDebugStringW(L"Bihua physical event rejected: truncated ABI.\\n");return 0;
  }
  BihuaPhysicalEventV1 event;memcpy(&event,m_request_channel->ReceivedPayload(),sizeof(event));
  if(!event.Valid()){OutputDebugStringW(L"Bihua physical event rejected: invalid ABI.\\n");return 0;}
  return m_pRequestHandler->PhysicalKeyEvent(event,session,[this](std::wstring& line){*m_request_channel<<line;return true;},command==WEASEL_IPC_PHYSICAL_QUERY);
}
#define MAP_PIPE_MSG_HANDLE'''),
('  PIPE_MSG_HANDLE(WEASEL_IPC_ECHO, OnEcho)','  PIPE_MSG_HANDLE(WEASEL_IPC_PHYSICAL_CAPABILITY, OnPhysicalKey)\n  PIPE_MSG_HANDLE(WEASEL_IPC_PHYSICAL_KEY, OnPhysicalKey)\n  PIPE_MSG_HANDLE(WEASEL_IPC_PHYSICAL_QUERY, OnPhysicalKey)\n  PIPE_MSG_HANDLE(WEASEL_IPC_ECHO, OnEcho)')])
edit('include/RimeWithWeasel.h',[
('  void _Setup();','  virtual DWORD PhysicalKeyEvent(const BihuaPhysicalEventV1& event,DWORD session,EatLine eat,bool query) override;\n  std::map<DWORD,std::array<bool,1024>> m_physical_keys;\n  bool _KeyboardTargetValid();\n  void _Setup();')])
edit('RimeWithWeasel/RimeWithWeasel.cpp',[
('void RimeWithWeaselHandler::FocusOut(DWORD param, WeaselSessionId ipc_id) {','void RimeWithWeaselHandler::FocusOut(DWORD param, WeaselSessionId ipc_id) {\n  m_physical_keys.erase(ipc_id);')])
path=SRC/'RimeWithWeasel/RimeWithWeasel.cpp';path.write_text(path.read_text(encoding='utf-8-sig')+'\n#include <BihuaPhysicalBackend.h>\n',encoding='utf-8-sig')
edit('WeaselTSF/KeyEventSink.cpp',[
('  if (!ConvertKeyEvent(static_cast<UINT>(wParam), lParam, _lpbKeyState, ke)) {','  KeyInfo physical_info(lParam);\n  UINT normalized=BihuaPhysicalKey::Normalize(static_cast<UINT>(wParam),physical_info.scanCode,physical_info.isExtended);\n  bool converted=ConvertKeyEvent(normalized,lParam,_lpbKeyState,ke);\n  if((GetKeyState(VK_LWIN)&0x8000)||(GetKeyState(VK_RWIN)&0x8000))ke.mask|=ibus::SUPER_MASK;\n  if (!converted) {'),
('    /* Unknown key event */\n    *pfEaten = FALSE;','    // Unknown VKs retain their physical identity even without a Rime name.\n    *pfEaten = m_client.ProcessPhysicalKeyEvent(static_cast<UINT>(wParam),lParam,ke);'),
('      *pfEaten = (BOOL)m_client.ProcessKeyEvent(ke);','      *pfEaten = (BOOL)m_client.ProcessPhysicalKeyEvent(static_cast<UINT>(wParam),lParam,ke);')])
for name in ['BihuaPhysicalKey.h','BihuaPhysicalBackend.h','BihuaFocusBoundary.h']:shutil.copy2(ROOT/'native'/name,SRC/'include'/name)
print('Physical event v1 server/client/TSF patch applied')
