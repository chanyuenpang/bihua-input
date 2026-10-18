#pragma once
#include <windows.h>
#include <filesystem>
// Resolve the peer from the OS pipe handle, never from client-supplied fields.
// Older Weasel startup scripts must not replace this user's dedicated server.
inline bool BihuaIsOtherServerCaller(HANDLE pipe) {
  ULONG pid=0;
  if(!GetNamedPipeClientProcessId(pipe,&pid))return false;
  HANDLE process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);
  if(!process)return false;
  wchar_t peer[32768]{},own[32768]{};DWORD length=32768;
  BOOL ok=QueryFullProcessImageNameW(process,0,peer,&length);CloseHandle(process);
  if(!ok)return false;
  GetModuleFileNameW(nullptr,own,32768);
  return _wcsicmp(std::filesystem::path(peer).filename().c_str(),L"WeaselServer.exe")==0 &&
         _wcsicmp(peer,own)!=0;
}
