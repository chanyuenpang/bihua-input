#pragma once
#include <windows.h>
#include <atomic>
#include <memory>
#include <thread>
#include <functional>
#include <cstdint>

// Pure transitions let probes exercise boundaries without OS keystrokes.
struct BihuaNumLockPolicy {
  bool active=false,original=false,held=false,captured=false;
  int Lease(bool next,bool current){
    if(next==active)return 0;
    if(next){original=current;active=true;return current?0:1;}
    active=false;return current==original?0:(original?1:-1);
  }
  // 0=pass, 1=suppress, 2=suppress and undo Windows' pre-hook toggle.
  int Key(bool down,bool eligible){
    if(!down){bool eat=captured;held=captured=false;return eat?1:0;}
    if(held)return captured?1:0;
    held=true;captured=eligible;return eligible?2:0;
  }
};

// One backend hook; only Num Lock under a live foreground TSF focus lease.
// No Rime calls, file access or UI locks occur inside the callback.
class BihuaNumLockGuard {
 public:
  ~BihuaNumLockGuard(){Stop();}
  std::function<void(const KBDLLHOOKSTRUCT&,uint64_t)> pressed;
  void Publish(HWND foreground,HWND focus,uint64_t generation=0){
    auto lease=std::make_shared<Lease>();lease->front=foreground;lease->focus=focus;
    lease->generation=generation;
    if(foreground)lease->thread=GetWindowThreadProcessId(foreground,&lease->pid);
    std::atomic_store(&published,std::shared_ptr<const Lease>(lease));
    if(thread_id)PostThreadMessageW(thread_id,RefreshMessage,0,0);
    if(!worker.joinable()&&foreground){
      stopping=false;
      try{worker=std::thread([this]{Run();});}catch(...){return;}
    }
  }
  void Stop(){
    stopping=true;
    if(worker.joinable()){if(thread_id)PostThreadMessageW(thread_id,WM_QUIT,0,0);worker.join();}
  }
 private:
  struct Lease{HWND front=nullptr,focus=nullptr;DWORD pid=0,thread=0;uint64_t generation=0;};
  std::shared_ptr<const Lease> published;
  std::thread worker;std::atomic<DWORD> thread_id{0};std::atomic<bool> stopping{false};
  HHOOK hook=nullptr;BihuaNumLockPolicy policy;
  bool pending_edge=false;KBDLLHOOKSTRUCT edge_key{};
  HWND edge_front=nullptr,edge_focus=nullptr;uint64_t edge_generation=0;
  inline static thread_local BihuaNumLockGuard* current=nullptr;
  static constexpr ULONG_PTR ownTag=0x42484e4c;
  static constexpr UINT RefreshMessage=WM_APP+97,EdgeMessage=WM_APP+98;
  bool Eligible(){
    auto lease=std::atomic_load(&published);
    if(!lease||!lease->front||GetForegroundWindow()!=lease->front)return false;
    GUITHREADINFO info{sizeof(info)};
    if(!GetGUIThreadInfo(lease->thread,&info)||info.hwndFocus!=lease->focus)return false;
    HDESK desktop=OpenInputDesktop(0,FALSE,DESKTOP_READOBJECTS);if(!desktop)return false;
    wchar_t name[64]{};DWORD size=0;
    bool normal=GetUserObjectInformationW(desktop,UOI_NAME,name,sizeof(name),&size)&&!_wcsicmp(name,L"Default");
    CloseDesktop(desktop);return normal;
  }
  static void Send(bool repair=false){
    INPUT keys[2]{};
    for(auto& key:keys){key.type=INPUT_KEYBOARD;key.ki.wVk=VK_NUMLOCK;key.ki.wScan=0x45;key.ki.dwExtraInfo=ownTag;key.ki.dwFlags=KEYEVENTF_EXTENDEDKEY;}
    keys[repair?0:1].ki.dwFlags|=KEYEVENTF_KEYUP;
    // Windows toggles before the hook. PowerToys documents the extra up/down
    // pair needed to restore the previous state when suppressing this key.
    SendInput(2,keys,sizeof(INPUT));
  }
  void Refresh(){
    bool eligible=Eligible();
    if(policy.held&&!eligible){pending_edge=false;return;}
    // Our synthetic events are suppressed before reaching an application
    // queue. While leased, use the state we enforce, not that queue's snapshot.
    if(policy.Lease(eligible,policy.active||(GetKeyState(VK_NUMLOCK)&1)!=0))Send();
    if(pending_edge){
      pending_edge=false;auto lease=std::atomic_load(&published);
      if(eligible&&lease&&lease->front==edge_front&&lease->focus==edge_focus&&lease->generation==edge_generation&&pressed)
        pressed(edge_key,edge_generation);
    }
  }
  static LRESULT CALLBACK Hook(int code,WPARAM wp,LPARAM lp){
    auto self=current;if(code<0||!self)return CallNextHookEx(nullptr,code,wp,lp);
    const auto& key=*reinterpret_cast<KBDLLHOOKSTRUCT*>(lp);
    if(key.vkCode!=VK_NUMLOCK)return CallNextHookEx(nullptr,code,wp,lp);
    if(key.dwExtraInfo==ownTag)return 1;
    if(key.flags&LLKHF_INJECTED)return CallNextHookEx(nullptr,code,wp,lp);
    bool down=wp==WM_KEYDOWN||wp==WM_SYSKEYDOWN;
    int action=self->policy.Key(down,self->policy.active&&self->Eligible());
    if(action==2){
      Send(true);
      bool modifiers=(GetAsyncKeyState(VK_CONTROL)&0x8000)||(GetAsyncKeyState(VK_MENU)&0x8000)||
        (GetAsyncKeyState(VK_SHIFT)&0x8000)||(GetAsyncKeyState(VK_LWIN)&0x8000)||(GetAsyncKeyState(VK_RWIN)&0x8000);
      auto lease=std::atomic_load(&self->published);
      if(!modifiers&&lease){self->edge_key=key;self->edge_front=lease->front;self->edge_focus=lease->focus;
        self->edge_generation=lease->generation;self->pending_edge=true;
        PostThreadMessageW(self->thread_id,EdgeMessage,0,0);}
    }
    return action?1:CallNextHookEx(nullptr,code,wp,lp);
  }
  void Run(){
    current=this;thread_id=GetCurrentThreadId();MSG message{};PeekMessageW(&message,nullptr,0,0,PM_NOREMOVE);
    hook=SetWindowsHookExW(WH_KEYBOARD_LL,Hook,GetModuleHandleW(nullptr),0);
    if(hook){
      Refresh();
      SetTimer(nullptr,1,40,nullptr);
      while(!stopping&&GetMessageW(&message,nullptr,0,0)>0){
        if(message.message==WM_TIMER||message.message==RefreshMessage||message.message==EdgeMessage)Refresh();
        else{TranslateMessage(&message);DispatchMessageW(&message);}
      }
      if(policy.active&&policy.Lease(false,true))Send();
      UnhookWindowsHookEx(hook);hook=nullptr;
    }
    thread_id=0;current=nullptr;
  }
};
