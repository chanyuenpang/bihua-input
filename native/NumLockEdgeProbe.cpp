#define UNICODE
#define _UNICODE
#include <windows.h>
#include <atomic>
#include <cassert>
#include <iostream>
#include <thread>
#include <functional>
static std::atomic<HWND> front{},focus{},hook_window{};
static std::atomic<bool> number_state{false},modifier{false};
static std::atomic<int> injected{0},called{0};
static thread_local bool in_hook=false;
static std::function<void()> revoke;
static std::atomic<bool> revoke_on_edge{false};
static HWND WINAPI ProbeFront(){return front;}
static BOOL WINAPI ProbeGui(DWORD,GUITHREADINFO* info){info->hwndFocus=focus;return TRUE;}
static SHORT WINAPI ProbeState(int){return number_state?1:0;}
static SHORT WINAPI ProbeAsync(int){return modifier?0x8000:0;}
static UINT WINAPI ProbeInput(UINT count,LPINPUT,int){assert(count==2);number_state=!number_state;++injected;return count;}
struct Event{WPARAM message;KBDLLHOOKSTRUCT key;};
static LRESULT CALLBACK HookWindow(HWND hwnd,UINT message,WPARAM,LPARAM lp){
  if(message==WM_APP+77){auto e=reinterpret_cast<Event*>(lp);auto callback=reinterpret_cast<HOOKPROC>(GetWindowLongPtrW(hwnd,GWLP_USERDATA));in_hook=true;auto result=callback(HC_ACTION,e->message,reinterpret_cast<LPARAM>(&e->key));in_hook=false;if(revoke_on_edge.exchange(false))revoke();return result;}
  return DefWindowProcW(hwnd,message,0,lp);
}
static HHOOK WINAPI ProbeInstall(int kind,HOOKPROC proc,HINSTANCE,DWORD){
  assert(kind==WH_KEYBOARD_LL);WNDCLASSW wc{};wc.lpfnWndProc=HookWindow;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"BihuaNumLockPrivateHook";RegisterClassW(&wc);
  auto h=CreateWindowW(wc.lpszClassName,L"",0,0,0,0,0,HWND_MESSAGE,nullptr,wc.hInstance,nullptr);assert(h);
  SetWindowLongPtrW(h,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(proc));hook_window=h;return reinterpret_cast<HHOOK>(h);
}
static BOOL WINAPI ProbeUninstall(HHOOK h){hook_window=nullptr;return DestroyWindow(reinterpret_cast<HWND>(h));}
#define GetForegroundWindow ProbeFront
#define GetGUIThreadInfo ProbeGui
#define GetKeyState ProbeState
#define GetAsyncKeyState ProbeAsync
#define SendInput ProbeInput
#define SetWindowsHookExW ProbeInstall
#define UnhookWindowsHookEx ProbeUninstall
#include "BihuaNumLock.h"
#undef GetForegroundWindow
#undef GetGUIThreadInfo
#undef GetKeyState
#undef GetAsyncKeyState
#undef SendInput
#undef SetWindowsHookExW
#undef UnhookWindowsHookEx
static void settle(){std::this_thread::sleep_for(std::chrono::milliseconds(130));}
static LRESULT key(bool down,DWORD flags=LLKHF_EXTENDED){Event e{};e.message=down?WM_KEYDOWN:WM_KEYUP;e.key.vkCode=VK_NUMLOCK;e.key.scanCode=0x45;e.key.flags=flags;return SendMessageW(hook_window,WM_APP+77,0,reinterpret_cast<LPARAM>(&e));}
int main(){
  auto h=CreateWindowW(L"STATIC",L"",0,0,0,0,0,HWND_MESSAGE,nullptr,GetModuleHandleW(nullptr),nullptr);assert(h);front=focus=h;
  for(bool original:{false,true}){
    number_state=original;int previous=called;BihuaNumLockGuard guard;
    guard.pressed=[&](const KBDLLHOOKSTRUCT& event,uint64_t generation){assert(!in_hook&&event.vkCode==VK_NUMLOCK&&generation==1);++called;};
    guard.Publish(h,h,1);settle();assert(number_state&&hook_window);
    number_state=false;assert(key(true)==1);for(int i=0;i<10;++i)assert(key(true)==1);assert(key(false)==1);
    settle();assert(called==previous+1&&number_state);
    modifier=true;number_state=false;assert(key(true)==1&&key(false)==1);settle();modifier=false;assert(called==previous+1&&number_state);
    assert(key(true,LLKHF_INJECTED)==0);assert(key(false,LLKHF_INJECTED)==0);settle();assert(called==previous+1);
    revoke=[&]{guard.Publish(h,h,2);};revoke_on_edge=true;
    number_state=false;assert(key(true)==1);key(false);settle();assert(called==previous+1);
    guard.Publish(nullptr,nullptr,3);settle();assert(number_state==original);guard.Stop();
  }
  DestroyWindow(h);
  std::cout<<"{\"result\":\"PASS\",\"hook_outside_callback\":true,\"one_edge_per_press\":true,\"modifiers_ignored\":true,\"injected_ignored\":true,\"stale_lease_rejected\":true,\"original_state_restored\":true,\"os_input_injected\":false}"<<std::endl;
}
