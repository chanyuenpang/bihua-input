#define UNICODE
#define _UNICODE
#include <windows.h>
#include <filesystem>
#include <iostream>
#include <cassert>
// Exercise the real listener branch with a private clipboard provider. Never
// replace the user's clipboard (which can contain images or delayed formats).
static DWORD sequence=1;static HGLOBAL data{};static bool blocked=false;
static DWORD WINAPI TestSequence(){return sequence;}
static BOOL WINAPI TestOpen(HWND){return !blocked;}
static BOOL WINAPI TestClose(){return TRUE;}
static BOOL WINAPI TestFormat(UINT f){return f==CF_UNICODETEXT;}
static HANDLE WINAPI TestData(UINT){return data;}
#define GetClipboardSequenceNumber TestSequence
#define OpenClipboard TestOpen
#define CloseClipboard TestClose
#define IsClipboardFormatAvailable TestFormat
#define GetClipboardData TestData
#include "BihuaMousePanel.h"
#undef GetClipboardSequenceNumber
#undef OpenClipboard
#undef CloseClipboard
#undef IsClipboardFormatAvailable
#undef GetClipboardData
static void pump(){MSG m;while(PeekMessageW(&m,nullptr,0,0,PM_REMOVE)){TranslateMessage(&m);DispatchMessageW(&m);}}
static void copy(HWND panel,const std::wstring& value){
  if(data)GlobalFree(data);data=GlobalAlloc(GMEM_MOVEABLE,(value.size()+1)*sizeof(wchar_t)+64);
  auto memory=GlobalLock(data);memcpy(memory,value.c_str(),(value.size()+1)*sizeof(wchar_t));GlobalUnlock(data);
  ++sequence;SendMessageW(panel,WM_CLIPBOARDUPDATE,0,0);pump();
}
int wmain(int argc,wchar_t**argv){
  _set_error_mode(_OUT_TO_STDERR);
  assert(argc==3);std::filesystem::path user=argv[1];std::filesystem::create_directories(user);
  HKEY sandbox{};auto key=L"Software\\BihuaInputMethodTests\\Personal-"+std::to_wstring(GetCurrentProcessId());
  assert(RegCreateKeyExW(HKEY_CURRENT_USER,key.c_str(),0,nullptr,0,KEY_ALL_ACCESS,nullptr,&sandbox,nullptr)==ERROR_SUCCESS);
  assert(RegOverridePredefKey(HKEY_CURRENT_USER,sandbox)==ERROR_SUCCESS);
  BihuaMousePanel panel;panel.ConfigurePersonal(user,argv[2],true,true);panel.Create();
  panel.SetProfileActive(true);panel.SetTargetActive(false);panel.SetModeAvailable(true);panel.SetKeyboardMode(0);
  weasel::UIStyle style;style.font_point=14;style.back_color=RGB(255,255,255);panel.Update(true,false,style,{},1);pump();
  int actions=0;panel.clicked=[&](int,int,uint32_t,uint64_t,uint64_t){++actions;};
  auto click=[&](int id){auto r=panel.ButtonRect(id);assert(!IsRectEmpty(&r));auto p=MAKELPARAM((r.left+r.right)/2,(r.top+r.bottom)/2);
    SendMessageW(panel.window,WM_LBUTTONDOWN,MK_LBUTTON,p);SendMessageW(panel.window,WM_LBUTTONUP,0,p);pump();};
  auto state=[&]{return LOWORD(SendMessageW(panel.window,WM_APP+49,0,0));};
  assert(IsWindowVisible(panel.window));click(0);assert(actions==0); // Disabled Rime stroke, still draggable.
  for(auto text:{L"国\n",L"中国",L"a",L"？",L"😀"}){copy(panel.window,text);assert(state()==0);}
  copy(panel.window,L"国");assert(state()==1);click(56);assert(state()==2);
  copy(panel.window,L"中");assert(state()==2); // New observations never replace a draft.
  click(0);click(1);click(2);click(3);click(4);click(17);click(4);assert(actions==0);
  click(58);for(int i=0;i<120&&state()!=0;++i){Sleep(50);SendMessageW(panel.window,WM_TIMER,1,0);pump();}
  assert(state()==0);std::ifstream file(user/L"bihua_personal_strokes.tsv");std::string content((std::istreambuf_iterator<char>(file)),{});
  assert(content.find("hspnz")!=std::string::npos&&content.find("\xe5\x9b\xbd")!=std::string::npos);
  copy(panel.window,L"国");assert(state()==1);click(56);click(17);click(0);click(58);
  for(int i=0;i<120&&HIWORD(SendMessageW(panel.window,WM_APP+49,0,0));++i){Sleep(50);SendMessageW(panel.window,WM_TIMER,1,0);pump();}
  assert(state()==2); // The open read handle intentionally denies atomic replace.
  file.close();click(58);
  for(int i=0;i<120&&state()!=0;++i){Sleep(50);SendMessageW(panel.window,WM_TIMER,1,0);pump();}assert(state()==0);
  panel.ObserveSelection(0x4e2d);pump();assert(state()==1);click(57);assert(state()==0);
  copy(panel.window,L"鼠");click(56);click(0);
  // Crossing the drag threshold on Save cannot publish anything.
  auto r=panel.ButtonRect(58);POINT p{(r.left+r.right)/2,(r.top+r.bottom)/2};
  SendMessageW(panel.window,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(p.x,p.y));
  SendMessageW(panel.window,WM_MOUSEMOVE,MK_LBUTTON,MAKELPARAM(p.x+40,p.y));
  SendMessageW(panel.window,WM_LBUTTONUP,0,MAKELPARAM(p.x,p.y));pump();assert(state()==2);
  panel.SetProfileActive(false);pump();assert(!IsWindowVisible(panel.window));panel.SetProfileActive(true);pump();assert(IsWindowVisible(panel.window)&&state()==2);
  click(57);assert(state()==0);assert(actions==0);
  int exposures=0;panel.displayed=[&](uint32_t,uint64_t,int,int){++exposures;};
  panel.SetTargetActive(true);panel.Update(true,true,style,{},2,{L"的",L"人"});pump();
  RedrawWindow(panel.window,nullptr,nullptr,RDW_INVALIDATE|RDW_UPDATENOW);int before_exposures=exposures;
  copy(panel.window,L"星");assert(state()==1);RedrawWindow(panel.window,nullptr,nullptr,RDW_INVALIDATE|RDW_UPDATENOW);
  assert(exposures==before_exposures); // Hidden predictions are never exposed or trained.
  click(57);assert(state()==0);
  if(data)GlobalFree(data);
  std::cout<<"PASS: no-focus compact, exact-Han clipboard listener, draft/save/overwrite, TSF offer, no Rime actions, drag, hide/restore\n";
}
