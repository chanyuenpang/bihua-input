#define UNICODE
#define _UNICODE
#include <windows.h>
#include <msctf.h>
#include <iostream>
#include <cassert>
int wmain(int argc,wchar_t** argv){
  if(argc!=2)return 2;
  CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
  auto module=LoadLibraryW(argv[1]);if(!module)return 3;
  auto version=reinterpret_cast<UINT(__cdecl*)()>(GetProcAddress(module,"BihuaGetPhysicalKeyProtocolVersion"));
  if(!version||version()!=1)return 4;
  const CLSID service={0x1d31bf35,0xf1b8,0x4352,{0x98,0x0e,0xb3,0x37,0x26,0x4d,0x82,0xfb}};
  auto get_factory=reinterpret_cast<HRESULT(__stdcall*)(REFCLSID,REFIID,void**)>(GetProcAddress(module,"DllGetClassObject"));
  IClassFactory* factory=nullptr;assert(get_factory&&SUCCEEDED(get_factory(service,IID_IClassFactory,reinterpret_cast<void**>(&factory))));
  ITfTextInputProcessor* processor=nullptr;assert(SUCCEEDED(factory->CreateInstance(nullptr,IID_ITfTextInputProcessor,reinterpret_cast<void**>(&processor))));
  ITfKeyEventSink* keys=nullptr;assert(SUCCEEDED(processor->QueryInterface(IID_ITfKeyEventSink,reinterpret_cast<void**>(&keys))));
  keys->Release();processor->Release();factory->Release();FreeLibrary(module);CoUninitialize();
  std::cout<<"{\"result\":\"PASS\",\"physical_protocol\":1,\"com_key_sink_created\":true,\"bits\":"<<sizeof(void*)*8<<"}"<<std::endl;
}
