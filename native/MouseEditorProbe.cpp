#define UNICODE
#define _UNICODE
#include <windows.h>
#include <msctf.h>
#include <richedit.h>
#include <string>
#include <fstream>
#include <filesystem>
#include <wrl/client.h>
using Microsoft::WRL::ComPtr;
static HWND field{},host{};static ComPtr<ITfThreadMgr> manager;static std::filesystem::path report;static HRESULT activate_result=E_PENDING;
static WNDPROC original_field_proc{};
static unsigned returns=0,keypad_returns=0,return_chars=0,return_ups=0;
static bool send_mode=false,last_down_eaten=false,last_up_eaten=false;
static LRESULT CALLBACK field_proc(HWND hwnd,UINT message,WPARAM wp,LPARAM lp){
  if(message==WM_KEYDOWN&&wp==VK_RETURN){++returns;if(lp&(1L<<24))++keypad_returns;if(send_mode)return 0;}
  if(message==WM_KEYUP&&wp==VK_RETURN)++return_ups;
  if(message==WM_CHAR&&wp==L'\r'){++return_chars;if(send_mode)return 0;}
  return CallWindowProcW(original_field_proc,hwnd,message,wp,lp);
}
static std::string json_escape(const char* text){
  std::string result;
  for(const unsigned char ch:std::string(text)){
    if(ch=='"'||ch=='\\'){result+='\\';result+=ch;}
    else if(ch=='\r')result+="\\r";
    else if(ch=='\n')result+="\\n";
    else if(ch=='\t')result+="\\t";
    else if(ch>=0x20)result+=ch;
  }
  return result;
}
static const CLSID service={0x1d31bf35,0xf1b8,0x4352,{0x98,0x0e,0xb3,0x37,0x26,0x4d,0x82,0xfb}};
static const GUID profile={0x49504670,0x200c,0x4a58,{0x9a,0x4f,0x72,0xb7,0xdc,0x6c,0xfb,0xa2}};
static HRESULT activate(){ComPtr<ITfInputProcessorProfileMgr> profiles;auto hr=CoCreateInstance(CLSID_TF_InputProcessorProfiles,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&profiles));if(FAILED(hr))return hr;return profiles->ActivateProfile(TF_PROFILETYPE_INPUTPROCESSOR,0x0804,service,profile,nullptr,TF_IPPMF_FORPROCESS|TF_IPPMF_DONTCARECURRENTINPUTLANGUAGE);}
static void snapshot(){
  ComPtr<ITfDocumentMgr> document;ComPtr<ITfContext> context;bool focused=manager&&SUCCEEDED(manager->GetFocus(&document))&&document&&SUCCEEDED(document->GetTop(&context))&&context;
  ComPtr<ITfCompartmentMgr> compartments;ComPtr<ITfCompartment> compartment;VARIANT open{};
  if(manager&&SUCCEEDED(manager.As(&compartments))&&SUCCEEDED(compartments->GetCompartment(GUID_COMPARTMENT_KEYBOARD_OPENCLOSE,&compartment)))compartment->GetValue(&open);
  ComPtr<ITfInputProcessorProfileMgr> profiles;TF_INPUTPROCESSORPROFILE active{};bool ours=false;
  if(SUCCEEDED(CoCreateInstance(CLSID_TF_InputProcessorProfiles,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&profiles))))ours=SUCCEEDED(profiles->GetActiveProfile(GUID_TFCAT_TIP_KEYBOARD,&active))&&IsEqualCLSID(active.clsid,service);
  TF_STATUS status{};if(context)context->GetStatus(&status);
  wchar_t text[2048]{};GetWindowTextW(field,text,2048);char utf8[8192]{};WideCharToMultiByte(CP_UTF8,0,text,-1,utf8,8192,nullptr,nullptr);
  // This controlled editor never reads or sends user documents or messages.
  std::ofstream file(report);file<<"{\"context\":"<<(focused?"true":"false")<<",\"foreground\":"<<(GetForegroundWindow()==host?"true":"false")<<",\"focus\":"<<(GetFocus()==field?"true":"false")<<",\"activate_hresult\":"<<activate_result<<",\"own_profile\":"<<(ours?"true":"false")<<",\"keyboard_open_type\":"<<open.vt<<",\"keyboard_open\":"<<open.lVal<<",\"dynamic_flags\":"<<status.dwDynamicFlags<<",\"new_frontend_loaded\":"<<((GetModuleHandleW(L"bihua64.dll")||GetModuleHandleW(L"bihua32.dll"))?"true":"false")<<",\"text\":\""<<json_escape(utf8)<<"\",\"return_down\":"<<returns<<",\"keypad_return_down\":"<<keypad_returns<<",\"return_chars\":"<<return_chars<<",\"return_up\":"<<return_ups<<",\"last_down_eaten\":"<<(last_down_eaten?"true":"false")<<",\"last_up_eaten\":"<<(last_up_eaten?"true":"false")<<"}";
}
static LRESULT CALLBACK proc(HWND hwnd,UINT message,WPARAM wp,LPARAM lp){
  if(message==WM_CREATE){field=CreateWindowW(L"RICHEDIT50W",L"",WS_CHILD|WS_VISIBLE|WS_BORDER|WS_TABSTOP|ES_MULTILINE,20,50,560,130,hwnd,reinterpret_cast<HMENU>(101),GetModuleHandleW(nullptr),nullptr);SendMessageW(field,EM_SETEDITSTYLE,SES_USECTF,SES_USECTF);original_field_proc=reinterpret_cast<WNDPROC>(SetWindowLongPtrW(field,GWLP_WNDPROC,reinterpret_cast<LONG_PTR>(field_proc)));CreateWindowW(L"STATIC",L"鼠标输入验证 · 仅此空白测试窗口",WS_CHILD|WS_VISIBLE,20,15,560,25,hwnd,nullptr,GetModuleHandleW(nullptr),nullptr);return 0;}
  if(message==WM_SETFOCUS){SetFocus(field);return 0;}
  if(message==WM_APP+90){snapshot();return 1;}
  if(message==WM_APP+91){ComPtr<ITfKeystrokeMgr> keys;BOOL eaten=FALSE;
    // This test process changes only its own queue's keyboard state, never the
    // user's system Caps Lock. TSF sees the same GetKeyState result as a key.
    if(wp==VK_CAPITAL){BYTE state[256]{};GetKeyboardState(state);state[VK_CAPITAL]^=1;SetKeyboardState(state);}
    LPARAM info=1|(MapVirtualKeyW(static_cast<UINT>(wp),MAPVK_VK_TO_VSC)<<16)|(lp&(1L<<24));if(manager&&SUCCEEDED(manager.As(&keys))){keys->TestKeyDown(wp,info,&eaten);if(eaten)keys->KeyDown(wp,info,&eaten);}last_down_eaten=!!eaten;if(!eaten){SendMessageW(field,WM_KEYDOWN,wp,info);if(wp==VK_RETURN)SendMessageW(field,WM_CHAR,L'\r',info);else if(wp>=L'A'&&wp<=L'Z')SendMessageW(field,WM_CHAR,((GetKeyState(VK_CAPITAL)&1)?L'A':L'a')+wp-L'A',info);else if(wp>=L'0'&&wp<=L'9')SendMessageW(field,WM_CHAR,wp,info);else if(wp>=VK_NUMPAD0&&wp<=VK_NUMPAD9)SendMessageW(field,WM_CHAR,L'0'+wp-VK_NUMPAD0,info);else if(wp==VK_SPACE)SendMessageW(field,WM_CHAR,L' ',info);else if(wp==VK_BACK)SendMessageW(field,WM_CHAR,L'\b',info);}PostMessageW(hwnd,WM_APP+96,wp,info|static_cast<LPARAM>(0xc0000000u));return 1;}
  if(message==WM_APP+102){BYTE state[256]{};GetKeyboardState(state);state[VK_CAPITAL]=static_cast<BYTE>((state[VK_CAPITAL]&~1)|(wp?1:0));SetKeyboardState(state);return 1;}
  if(message==WM_APP+103){SetWindowTextW(field,L"国");SendMessageW(field,EM_SETSEL,0,1);return 1;}
  if(message==WM_APP+96){ComPtr<ITfKeystrokeMgr> keys;BOOL eaten=FALSE;if(manager&&SUCCEEDED(manager.As(&keys))){keys->TestKeyUp(wp,lp,&eaten);if(eaten)keys->KeyUp(wp,lp,&eaten);}last_up_eaten=!!eaten;if(!eaten)SendMessageW(field,WM_KEYUP,wp,lp);return 1;}
  if(message==WM_APP+101){ComPtr<ITfKeystrokeMgr> keys;BOOL eaten=FALSE;
    LPARAM info=1|(MapVirtualKeyW(static_cast<UINT>(wp),MAPVK_VK_TO_VSC)<<16);
    if(manager&&SUCCEEDED(manager.As(&keys))){
      if(lp){info|=static_cast<LPARAM>(0xc0000000u);keys->TestKeyUp(wp,info,&eaten);if(eaten)keys->KeyUp(wp,info,&eaten);}
      else{keys->TestKeyDown(wp,info,&eaten);if(eaten)keys->KeyDown(wp,info,&eaten);}
    }return 1;}
  if(message==WM_APP+99){send_mode=!!wp;return 1;}
  if(message==WM_APP+92){ShowWindow(hwnd,SW_RESTORE);SetForegroundWindow(hwnd);SetFocus(field);activate_result=activate();return 1;}
  if(message==WM_APP+93){SendMessageW(field,EM_SETREADONLY,wp,0);SetFocus(nullptr);SetFocus(field);return 1;}
  if(message==WM_APP+100){SendMessageW(field,EM_SETREADONLY,wp,0);return 1;}
  if(message==WM_APP+94){SetFocus(nullptr);return 1;}
  if(message==WM_APP+97){ShowWindow(hwnd,SW_RESTORE);SetForegroundWindow(hwnd);SetFocus(field);return 1;}
  if(message==WM_APP+98)return AllowSetForegroundWindow(static_cast<DWORD>(wp));
  if(message==WM_APP+95){ComPtr<ITfInputProcessorProfileMgr> profiles;if(SUCCEEDED(CoCreateInstance(CLSID_TF_InputProcessorProfiles,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&profiles))))profiles->ActivateProfile(TF_PROFILETYPE_KEYBOARDLAYOUT,0x0409,CLSID_NULL,GUID_NULL,LoadKeyboardLayoutW(L"00000409",0),TF_IPPMF_FORPROCESS|TF_IPPMF_DONTCARECURRENTINPUTLANGUAGE);return 1;}
  if(message==WM_CLOSE){DestroyWindow(hwnd);return 0;}
  if(message==WM_DESTROY){PostQuitMessage(0);return 0;}
  return DefWindowProcW(hwnd,message,wp,lp);
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE,PWSTR command,int){
  report=command;CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);LoadLibraryW(L"msftedit.dll");
  TfClientId client=0;CoCreateInstance(CLSID_TF_ThreadMgr,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&manager));if(manager)manager->Activate(&client);
  WNDCLASSW cls{};cls.lpfnWndProc=proc;cls.hInstance=instance;cls.hCursor=LoadCursor(nullptr,IDC_ARROW);cls.hbrBackground=reinterpret_cast<HBRUSH>(COLOR_WINDOW+1);cls.lpszClassName=L"BihuaMouseEditorProbe";RegisterClassW(&cls);
  host=CreateWindowW(cls.lpszClassName,L"笔画鼠标输入验证",WS_OVERLAPPEDWINDOW,100,100,640,270,nullptr,nullptr,instance,nullptr);
  ShowWindow(host,SW_SHOW);SetForegroundWindow(host);SetFocus(field);activate_result=activate();
  MSG msg;while(GetMessageW(&msg,nullptr,0,0)>0){TranslateMessage(&msg);DispatchMessageW(&msg);}
  if(manager)manager->Deactivate();manager.Reset();CoUninitialize();return 0;
}
