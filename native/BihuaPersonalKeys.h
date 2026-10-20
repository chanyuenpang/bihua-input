#pragma once
#include <windows.h>
#include "BihuaPhysicalKey.h"
#include <array>
#include <atomic>
#include <memory>
#include <string>
#include <thread>

// Read-only projection shared with ordinary TSF input.
struct BihuaPersonalKeyMap : BihuaPhysicalBindings {
  template<class Reader>static BihuaPersonalKeyMap Read(Reader read){
    BihuaPersonalKeyMap result;
    static_cast<BihuaPhysicalBindings&>(result)=BihuaPhysicalBindings::Read(read);return result;
  }
  static UINT Physical(const KBDLLHOOKSTRUCT& key){
    return BihuaPhysicalKey::Normalize(key.vkCode,key.scanCode,!!(key.flags&LLKHF_EXTENDED));
  }
  int Action(const KBDLLHOOKSTRUCT& key)const{
    auto value=Physical(key);
    if(value==VK_BACK)return 5;
    if(value==VK_RETURN)return 6;
    if(value==VK_ESCAPE)return 7;
    BihuaPhysicalEventV1 event;event.vk=key.vkCode;event.scan=key.scanCode;
    event.flags=(key.flags&LLKHF_EXTENDED)?BihuaPhysicalEventV1::Extended:0;
    int action=Resolve(event,true);
    if(action>=0)return action<5?action:8;
    if(value>=0x30&&value<=0x5a||value>=VK_NUMPAD0&&value<=VK_DIVIDE||value>=VK_OEM_1&&value<=VK_OEM_102||value==VK_SPACE)return 9;
    return -1;
  }
};

// Draft-only hook. The dedicated message thread never touches Rime, files or
// the UI mutex. Actions are posted to the one UI-thread recorder owner.
class BihuaPersonalKeyCapture {
 public:
  static constexpr UINT ActionMessage=WM_APP+50;
  enum { Paused=10, Unavailable=11 };
  std::atomic<bool> active{false},allowed{false};
  ~BihuaPersonalKeyCapture(){Stop();}
  static bool DefaultDesktop(){
    HDESK desktop=OpenInputDesktop(0,FALSE,DESKTOP_READOBJECTS);if(!desktop)return false;
    wchar_t name[64]{};DWORD size=0;bool ok=GetUserObjectInformationW(desktop,UOI_NAME,name,sizeof(name),&size)&&!_wcsicmp(name,L"Default");CloseDesktop(desktop);return ok;
  }
  static bool SafeForeground(HWND front){
    if(!front||!IsWindow(front)||!DefaultDesktop())return false;
    DWORD pid=0,thread=GetWindowThreadProcessId(front,&pid);if(!pid||!thread)return false;
    HANDLE process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);if(!process)return false;
    HANDLE token=nullptr;bool safe=false;
    if(OpenProcessToken(process,TOKEN_QUERY,&token)){
      BYTE buffer[512]{};DWORD size=0;
      if(GetTokenInformation(token,TokenIntegrityLevel,buffer,sizeof(buffer),&size)){
        auto label=reinterpret_cast<TOKEN_MANDATORY_LABEL*>(buffer);
        auto sid=label->Label.Sid;auto level=*GetSidSubAuthority(sid,*GetSidSubAuthorityCount(sid)-1);
        safe=level<SECURITY_MANDATORY_HIGH_RID;
      }
      CloseHandle(token);
    }
    CloseHandle(process);
    GUITHREADINFO gui{sizeof(gui)};
    if(safe&&GetGUIThreadInfo(thread,&gui)&&gui.hwndFocus){
      wchar_t name[64]{};GetClassNameW(gui.hwndFocus,name,64);
      if(!_wcsicmp(name,L"Edit")&&(GetWindowLongPtrW(gui.hwndFocus,GWL_STYLE)&ES_PASSWORD))safe=false;
    }
    return safe;
  }
  bool Arm(HWND target,HWND front,const BihuaPersonalKeyMap& map,uint64_t serial){
    if(!map.valid||!SafeForeground(front)){Pause();return false;}
    if(!worker.joinable()){
      stopping=false;
      ready=CreateEventW(nullptr,TRUE,FALSE,nullptr);arm_ready=CreateEventW(nullptr,TRUE,FALSE,nullptr);
      if(!ready||!arm_ready){Stop();return false;}
      try{worker=std::thread([this]{Run();});}catch(...){Stop();return false;}
      if(WaitForSingleObject(ready,2000)!=WAIT_OBJECT_0){Stop();return false;}
    }
    auto command=std::make_unique<Lease>();command->target=target;command->front=front;command->focus=FocusOf(front);command->map=map;command->serial=serial;
    ResetEvent(arm_ready);active=false;requested=serial;allowed=true;
    if(!PostThreadMessageW(thread_id,ArmMessage,0,reinterpret_cast<LPARAM>(command.get()))){allowed=false;return false;}
    command.release();
    if(WaitForSingleObject(arm_ready,500)!=WAIT_OBJECT_0||!active||requested!=serial){Pause();return false;}
    return true;
  }
  void Pause(){requested=0;allowed=false;if(thread_id)PostThreadMessageW(thread_id,PauseMessage,0,0);}
  void Stop(){
    stopping=true;requested=0;allowed=false;
    if(worker.joinable()){PostThreadMessageW(thread_id,WM_QUIT,0,0);worker.join();}
    thread_id=0;if(ready){CloseHandle(ready);ready=nullptr;}if(arm_ready){CloseHandle(arm_ready);arm_ready=nullptr;}
  }
  // The same pure transition runs in the real hook and the native probe.
  struct Ledger {
    std::array<bool,1024> held{},eaten{};
    bool Any()const {for(bool value:eaten)if(value)return true;return false;}
    bool Route(const KBDLLHOOKSTRUCT& key,bool down,bool armed,const BihuaPersonalKeyMap& map,int& action){
      action=-1;if(key.flags&LLKHF_INJECTED)return false;
      unsigned id=(key.scanCode?(key.scanCode&255):512+(key.vkCode&255))+((key.flags&LLKHF_EXTENDED)?256:0);
      if(!down){bool eat=eaten[id];held[id]=eaten[id]=false;return eat;}
      if(held[id])return eaten[id];held[id]=true;
      if(!armed)return false;
      action=map.Action(key);if(action<0)return false;
      eaten[id]=true;return true;
    }
  };
 private:
  static constexpr UINT ArmMessage=WM_APP+61,PauseMessage=WM_APP+62;
  struct Lease{HWND target=nullptr,front=nullptr,focus=nullptr;BihuaPersonalKeyMap map;uint64_t serial=0;};
  inline static thread_local BihuaPersonalKeyCapture* current=nullptr;
  std::thread worker;DWORD thread_id=0;HANDLE ready=nullptr,arm_ready=nullptr;HHOOK hook=nullptr;
  Lease lease;Ledger ledger;bool accepting=false;ULONGLONG paused_at=0;
  std::atomic<uint64_t> requested{0};
  std::atomic<bool> stopping{false};
  static HWND FocusOf(HWND front){GUITHREADINFO gui{sizeof(gui)};auto thread=GetWindowThreadProcessId(front,nullptr);return thread&&GetGUIThreadInfo(thread,&gui)?gui.hwndFocus:nullptr;}
  void Notify(int action){if(lease.target)PostMessageW(lease.target,ActionMessage,static_cast<WPARAM>(lease.serial),action);}
  void Suspend(bool notify=true){
    bool was=accepting;accepting=false;active=false;allowed=false;paused_at=GetTickCount64();
    if(requested==lease.serial)requested=0;
    if(notify&&was)Notify(Paused);
    if(hook&&!ledger.Any()){UnhookWindowsHookEx(hook);hook=nullptr;}
  }
  static LRESULT CALLBACK Hook(int code,WPARAM wp,LPARAM lp){
    auto self=current;if(code<0||!self)return CallNextHookEx(nullptr,code,wp,lp);
    const auto& key=*reinterpret_cast<KBDLLHOOKSTRUCT*>(lp);
    if(key.flags&LLKHF_INJECTED)return CallNextHookEx(nullptr,code,wp,lp);
    bool down=wp==WM_KEYDOWN||wp==WM_SYSKEYDOWN;
    if(down&&(key.vkCode==VK_CONTROL||key.vkCode==VK_LCONTROL||key.vkCode==VK_RCONTROL||
        key.vkCode==VK_MENU||key.vkCode==VK_LMENU||key.vkCode==VK_RMENU||key.vkCode==VK_LWIN||key.vkCode==VK_RWIN))self->Suspend();
    if(self->accepting&&(!self->allowed||self->requested!=self->lease.serial||GetForegroundWindow()!=self->lease.front||FocusOf(self->lease.front)!=self->lease.focus))self->Suspend();
    int action=-1;bool eat=self->ledger.Route(key,down,self->accepting&&self->allowed,self->lease.map,action);
    if(eat&&down&&action>=0)self->Notify(action);
    if(key.vkCode==VK_NUMLOCK)return CallNextHookEx(nullptr,code,wp,lp);
    if(!self->accepting&&self->hook&&!self->ledger.Any()){UnhookWindowsHookEx(self->hook);self->hook=nullptr;}
    return eat?1:CallNextHookEx(nullptr,code,wp,lp);
  }
  void Run(){
    current=this;thread_id=GetCurrentThreadId();MSG message{};PeekMessageW(&message,nullptr,0,0,PM_NOREMOVE);SetEvent(ready);
    SetTimer(nullptr,1,80,nullptr);
    while(!stopping&&GetMessageW(&message,nullptr,0,0)>0){
      if(message.message==ArmMessage){
        std::unique_ptr<Lease> next(reinterpret_cast<Lease*>(message.lParam));
        Suspend(false);lease=*next;
        if(requested!=lease.serial||!SafeForeground(lease.front)||GetForegroundWindow()!=lease.front){Suspend(false);Notify(Unavailable);SetEvent(arm_ready);continue;}
        allowed=true;
        // Key-ups from the uncaptured interval were never observed. Retain a
        // ledger only while an existing hook is draining captured presses.
        if(!hook){ledger={};hook=SetWindowsHookExW(WH_KEYBOARD_LL,Hook,GetModuleHandleW(nullptr),0);}
        if(!hook){Suspend(false);Notify(Unavailable);SetEvent(arm_ready);continue;}
        accepting=true;active=true;
        if(GetAsyncKeyState(VK_CONTROL)&0x8000||GetAsyncKeyState(VK_MENU)&0x8000||GetAsyncKeyState(VK_LWIN)&0x8000||GetAsyncKeyState(VK_RWIN)&0x8000)Suspend();
        SetEvent(arm_ready);
      }else if(message.message==PauseMessage)Suspend();
      else if(message.message==WM_TIMER){
        if(accepting&&(!allowed||requested!=lease.serial||GetForegroundWindow()!=lease.front||FocusOf(lease.front)!=lease.focus||!SafeForeground(lease.front)))Suspend();
        if(!accepting&&hook&&GetTickCount64()-paused_at>5000){UnhookWindowsHookEx(hook);hook=nullptr;ledger={};}
      }else{TranslateMessage(&message);DispatchMessageW(&message);}
    }
    if(hook)UnhookWindowsHookEx(hook);hook=nullptr;active=false;allowed=false;
    while(PeekMessageW(&message,nullptr,ArmMessage,ArmMessage,PM_REMOVE))delete reinterpret_cast<Lease*>(message.lParam);
    current=nullptr;
  }
};
