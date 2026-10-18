#define UNICODE
#define _UNICODE
#include "BihuaLegacyStartup.h"
#include <cassert>
#include <iostream>
int wmain(int argc,wchar_t**argv){
  _set_error_mode(_OUT_TO_STDERR);assert(argc==2);
  auto key=L"Software\\BihuaInputMethodTests\\Legacy-"+std::to_wstring(GetCurrentProcessId());HKEY handle{};
  assert(RegCreateKeyExW(HKEY_CURRENT_USER,key.c_str(),0,nullptr,0,KEY_ALL_ACCESS,nullptr,&handle,nullptr)==0);
  auto set=[&](const wchar_t* name,const std::wstring& value){assert(RegSetValueExW(handle,name,0,REG_SZ,reinterpret_cast<const BYTE*>(value.c_str()),static_cast<DWORD>((value.size()+1)*2))==0);};
  auto get=[&](const wchar_t* name){wchar_t text[2048]{};DWORD size=sizeof(text);return RegQueryValueExW(handle,name,nullptr,nullptr,reinterpret_cast<BYTE*>(text),&size)==ERROR_SUCCESS?std::wstring(text):L"<absent>";};
  const std::wstring exact=L"C:\\Program Files\\Rime\\weasel-0.17.4\\WeaselServer.exe";
  set(L"retire",exact);set(L"quoted",L"\""+exact+L"\"");set(L"WeaselServer",exact+L" /unknown");set(L"unrelated",L"C:\\Other\\WeaselServer.exe");
  BihuaLegacyStartup cleanup;cleanup.root=HKEY_CURRENT_USER;cleanup.key=key;
  assert(cleanup.Retire(argv[1],exact)==0);assert(cleanup.removed.size()==2);
  assert(get(L"retire")==L"<absent>"&&get(L"quoted")==L"<absent>");assert(get(L"WeaselServer")==exact+L" /unknown"&&get(L"unrelated")==L"C:\\Other\\WeaselServer.exe");
  assert(cleanup.Rollback()==0);assert(get(L"retire")==exact&&get(L"quoted")==L"\""+exact+L"\"");
  assert(cleanup.Retire(argv[1],exact)==0);set(L"retire",L"administrator changed");assert(cleanup.Rollback()==ERROR_ALREADY_EXISTS);
  assert(get(L"retire")==L"administrator changed"&&get(L"quoted")==L"\""+exact+L"\"");
  RegCloseKey(handle);RegDeleteTreeW(HKEY_CURRENT_USER,key.c_str());
  std::cout<<"PASS: exact executable only, backup, unknown parameters/path unchanged, rollback, concurrent-value protection\n";
}
