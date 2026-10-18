#define UNICODE
#include <windows.h>
#include <objbase.h>
#include <stdio.h>
int wmain() {
  CoInitialize(nullptr);
  CLSID clsid{}; CLSIDFromString(L"{A3F4CDED-B1E9-41EE-9CA6-7B4D0DE6CB0A}",&clsid);
  IUnknown* object=nullptr;
  HRESULT result=CoCreateInstance(clsid,nullptr,CLSCTX_INPROC_SERVER,IID_IUnknown,reinterpret_cast<void**>(&object));
  if(FAILED(result)){wprintf(L"COM failed: %08x\n",static_cast<unsigned>(result));return 1;}
  wchar_t path[32768]{};
#ifdef _WIN64
  auto module=GetModuleHandleW(L"weaselx64.dll");
#else
  auto module=GetModuleHandleW(L"weasel.dll");
#endif
  if (!module) {object->Release();CoUninitialize();return 2;}
  GetModuleFileNameW(module,path,32768);wprintf(L"%ls\n",path);
  object->Release();CoUninitialize();return 0;
}
