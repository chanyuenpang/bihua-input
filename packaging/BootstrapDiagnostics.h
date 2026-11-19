#pragma once
#include <windows.h>
#include <filesystem>
#include <fstream>
#include <string>
#include <stdexcept>
#include <vector>

namespace BihuaSetup {
namespace fs=std::filesystem;
inline std::string Utf8(const std::wstring& text){
  if(text.empty())return {};
  int count=WideCharToMultiByte(CP_UTF8,0,text.data(),static_cast<int>(text.size()),nullptr,0,nullptr,nullptr);
  std::string out(count,'\0');WideCharToMultiByte(CP_UTF8,0,text.data(),static_cast<int>(text.size()),out.data(),count,nullptr,nullptr);return out;
}
inline std::wstring Wide(const std::string& text){
  if(text.empty())return {};
  UINT page=CP_UTF8;int count=MultiByteToWideChar(page,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),nullptr,0);
  if(!count){page=CP_ACP;count=MultiByteToWideChar(page,0,text.data(),static_cast<int>(text.size()),nullptr,0);}
  std::wstring out(count,L'\0');MultiByteToWideChar(page,0,text.data(),static_cast<int>(text.size()),out.data(),count);return out;
}
inline std::wstring Hex(DWORD value){wchar_t buffer[16]{};swprintf_s(buffer,L"0x%08lX",value);return buffer;}
inline std::wstring WinError(DWORD value){
  wchar_t* raw=nullptr;
  FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER|FORMAT_MESSAGE_FROM_SYSTEM|FORMAT_MESSAGE_IGNORE_INSERTS,nullptr,value,0,reinterpret_cast<LPWSTR>(&raw),0,nullptr);
  std::wstring out=raw?raw:L"Windows 未返回错误说明";if(raw)LocalFree(raw);
  while(!out.empty()&&(out.back()==L'\r'||out.back()==L'\n'))out.pop_back();
  return out+L"（"+Hex(value)+L"）";
}
struct Failure:std::runtime_error{
  std::wstring detail;
  explicit Failure(const std::wstring& text):std::runtime_error(Utf8(text)),detail(text){}
};
class Diagnostics {
 public:
  fs::path path;
  std::wstring stage=L"准备安装",log_error;
  void Begin(const fs::path& executable){
    path.clear();log_error.clear();stage=L"准备安装";
    GUID id{};CoCreateGuid(&id);wchar_t unique[48]{};StringFromGUID2(id,unique,48);
    wchar_t temp[32768]{};DWORD length=GetTempPathW(32768,temp);
    std::vector<fs::path> folders;
    if(length&&length<32768)folders.emplace_back(temp);
    folders.push_back(executable.parent_path());
    for(const auto& folder:folders){
      auto candidate=folder/(L"BihuaInput-Setup-"+std::to_wstring(GetCurrentProcessId())+L"-"+unique+L".log");
      HANDLE file=CreateFileW(candidate.c_str(),GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
      if(file==INVALID_HANDLE_VALUE){log_error=WinError(GetLastError());continue;}
      const char bom[]="\xef\xbb\xbf";DWORD written=0;
      if(!WriteFile(file,bom,3,&written,nullptr)||written!=3){log_error=WinError(GetLastError());CloseHandle(file);continue;}
      path=candidate;
      // An MSIX parent may redirect AppData. Show the actual file Explorer can
      // open, rather than the logical path inherited from that process.
      wchar_t final_name[32768]{};DWORD count=GetFinalPathNameByHandleW(file,final_name,32768,0);
      if(count&&count<32768){std::wstring physical=final_name;
        if(physical.rfind(L"\\\\?\\UNC\\",0)==0)physical=L"\\\\"+physical.substr(8);
        else if(physical.rfind(L"\\\\?\\",0)==0)physical=physical.substr(4);
        path=physical;
      }
      CloseHandle(file);break;
    }
    SYSTEMTIME time{};GetLocalTime(&time);SYSTEM_INFO machine{};GetNativeSystemInfo(&machine);
    Write(L"笔画输入法安装诊断\r\nInstaller: "+executable.wstring()+L"\r\nPID: "+std::to_wstring(GetCurrentProcessId())+
      L"\r\nTime: "+std::to_wstring(time.wYear)+L"-"+std::to_wstring(time.wMonth)+L"-"+std::to_wstring(time.wDay)+L" "+std::to_wstring(time.wHour)+L":"+std::to_wstring(time.wMinute)+
      L"\r\nNative processor architecture: "+std::to_wstring(machine.wProcessorArchitecture)+L"\r\n");
    using VersionFn=LONG(WINAPI*)(OSVERSIONINFOW*);
    auto version=reinterpret_cast<VersionFn>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"RtlGetVersion"));
    OSVERSIONINFOW windows{sizeof(windows)};
    if(version&&version(&windows)>=0)Write(L"Windows: "+std::to_wstring(windows.dwMajorVersion)+L"."+std::to_wstring(windows.dwMinorVersion)+L"."+std::to_wstring(windows.dwBuildNumber)+L"\r\n");
    using PackageFn=LONG(WINAPI*)(UINT32*,PWSTR);
    auto package=reinterpret_cast<PackageFn>(GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"GetCurrentPackageFullName"));
    UINT32 count=0;
    if(package&&package(&count,nullptr)==ERROR_INSUFFICIENT_BUFFER){std::wstring identity(count,L'\0');if(!package(&count,identity.data()))Write(std::wstring(L"Package context: ")+identity.c_str()+L"\r\n");}
  }
  void Write(const std::wstring& value){
    if(path.empty())return;
    std::ofstream file(path,std::ios::binary|std::ios::app);auto bytes=Utf8(value);file.write(bytes.data(),bytes.size());file.flush();
  }
  void Step(const std::wstring& value){stage=value;Write(L"\r\n[阶段] "+value+L"\r\n");}
  DWORD Run(const fs::path& exe,const std::wstring& parameters,DWORD timeout=240000){
    Write(L"Executable: "+exe.wstring()+L"\r\nArguments: "+parameters+L"\r\n");
    SECURITY_ATTRIBUTES attributes{sizeof(attributes),nullptr,TRUE};
    HANDLE output=path.empty()?INVALID_HANDLE_VALUE:CreateFileW(path.c_str(),GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,&attributes,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    HANDLE input=CreateFileW(L"NUL",GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,&attributes,OPEN_EXISTING,0,nullptr);
    if(output!=INVALID_HANDLE_VALUE)SetFilePointer(output,0,nullptr,FILE_END);
    STARTUPINFOW start{sizeof(start)};start.dwFlags=STARTF_USESHOWWINDOW;start.wShowWindow=SW_HIDE;
    if(output!=INVALID_HANDLE_VALUE&&input!=INVALID_HANDLE_VALUE){start.dwFlags|=STARTF_USESTDHANDLES;start.hStdOutput=start.hStdError=output;start.hStdInput=input;}
    std::wstring command=L"\""+exe.wstring()+L"\" "+parameters;PROCESS_INFORMATION process{};
    BOOL launched=CreateProcessW(exe.c_str(),command.data(),nullptr,nullptr,!!(start.dwFlags&STARTF_USESTDHANDLES),CREATE_NO_WINDOW,nullptr,exe.parent_path().c_str(),&start,&process);
    DWORD error=launched?0:GetLastError();
    if(input!=INVALID_HANDLE_VALUE)CloseHandle(input);
    if(output!=INVALID_HANDLE_VALUE)CloseHandle(output);
    if(!launched)throw Failure(L"无法启动 "+exe.filename().wstring()+L"："+WinError(error));
    DWORD waited=WaitForSingleObject(process.hProcess,timeout),result=1;
    if(waited==WAIT_TIMEOUT){
      Write(L"\r\n安装步骤仍在运行，继续等待。请勿重复安装。\r\n");
      waited=WaitForSingleObject(process.hProcess,INFINITE);
    }
    bool exited=waited==WAIT_OBJECT_0&&GetExitCodeProcess(process.hProcess,&result);
    error=exited?0:GetLastError();CloseHandle(process.hThread);CloseHandle(process.hProcess);
    if(!exited)throw Failure(L"无法取得安装步骤结果："+WinError(error));
    Write(L"\r\nExit code: "+std::to_wstring(result)+L" ("+Hex(result)+L")\r\n");return result;
  }
  std::wstring OutputTail(){
    if(path.empty())return {};
    std::ifstream file(path,std::ios::binary);if(!file)return {};
    file.seekg(0,std::ios::end);auto size=file.tellg();
    auto begin=size>std::streamoff(8192)?size-std::streamoff(8192):std::streampos(0);file.seekg(begin);
    std::string bytes((std::istreambuf_iterator<char>(file)),{});auto text=Wide(bytes);
    auto exit=text.rfind(L"\r\nExit code:");if(exit!=std::wstring::npos)text.resize(exit);
    auto newline=text.rfind(L'\n');while(!text.empty()&&(text.back()==L'\n'||text.back()==L'\r'))text.pop_back();
    if(text.size()>900)text=L"…"+text.substr(text.size()-900);return text;
  }
  std::wstring Report(const std::wstring& error){
    std::wstring detail=L"失败阶段："+stage+L"\r\n"+error;
    Write(L"\r\n[失败] "+detail+L"\r\n");
    std::error_code check;
    if(!path.empty()&&fs::exists(path,check))detail+=L"\r\n\r\n诊断日志：\r\n"+path.wstring();
    else detail+=L"\r\n\r\n未能创建诊断日志："+log_error;
    return detail;
  }
};
}
