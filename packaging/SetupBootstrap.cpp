#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <shlobj.h>
#include <commctrl.h>
#include <wincrypt.h>
#include <filesystem>
#include <fstream>
#include <string>
#include <thread>
#include <stdexcept>
#include "BootstrapDiagnostics.h"

namespace fs=std::filesystem;
static HWND window{},status{},button{};
static std::wstring last_error;
static bool working=false,finished=false;
static BihuaSetup::Diagnostics diagnostics;
static std::wstring hash_bytes(const void* bytes,DWORD length) {
  BYTE digest[32]{};DWORD size=sizeof(digest);
  if(!CryptHashCertificate2(L"SHA256",0,nullptr,static_cast<const BYTE*>(bytes),length,digest,&size))
    throw BihuaSetup::Failure(L"无法校验安装资源："+BihuaSetup::WinError(GetLastError()));
  std::wstring result;for(auto value:digest){wchar_t pair[3]{};swprintf_s(pair,L"%02x",value);result+=pair;}return result;
}
static constexpr auto product_mutex = L"Local\\BihuaInputSetup";
class SetupLock {
  HANDLE mutex{};
public:
  SetupLock(const std::wstring& name, const wchar_t* busy_message) {
    if(name.empty())return;
    mutex=CreateMutexW(nullptr,FALSE,name.c_str());
    if(!mutex)throw BihuaSetup::Failure(L"无法建立安装锁："+BihuaSetup::WinError(GetLastError()));
    const auto wait=WaitForSingleObject(mutex,0);
    if(wait!=WAIT_OBJECT_0&&wait!=WAIT_ABANDONED){
      CloseHandle(mutex);
      throw BihuaSetup::Failure(busy_message);
    }
  }
  SetupLock(const SetupLock&)=delete;
  SetupLock& operator=(const SetupLock&)=delete;
  ~SetupLock(){
    if(mutex){ReleaseMutex(mutex);CloseHandle(mutex);}
  }
};
static std::wstring destination_lock_name(const fs::path& target) {
  auto path=fs::absolute(target).lexically_normal().wstring();for(auto& ch:path)ch=towupper(ch);
  return L"Local\\BihuaSetup-"+hash_bytes(path.data(),static_cast<DWORD>(path.size()*sizeof(wchar_t)));
}
static constexpr auto retry_product = L"另一个安装程序正在配置笔画输入法，请等待它完成。";
static constexpr auto retry_destination = L"另一个安装程序正在处理此目录，请等待它完成。";
static std::wstring quote(const std::wstring& text) { return L"\""+text+L"\""; }
static std::wstring psquote(std::wstring text) {
  size_t pos=0;while((pos=text.find(L"'",pos))!=std::wstring::npos){text.insert(pos,L"'");pos+=2;}
  return L"'"+text+L"'";
}
static DWORD execute(const fs::path& exe,const std::wstring& parameters) {
  return diagnostics.Run(exe,parameters);
}
static fs::path own_directory() {wchar_t path[32768]{};GetModuleFileNameW(nullptr,path,32768);return fs::path(path).parent_path();}
static fs::path destination() {
  PWSTR local{};if(FAILED(SHGetKnownFolderPath(FOLDERID_LocalAppData,0,nullptr,&local)))throw std::runtime_error("Cannot find LocalAppData");
  fs::path result=fs::path(local)/L"BihuaWeasel"/L"0.6.44";CoTaskMemFree(local);return result;
}
static fs::path powershell() {wchar_t system[32768]{};GetSystemDirectoryW(system,32768);return fs::path(system)/L"WindowsPowerShell/v1.0/powershell.exe";}
static void cleanup_after_exit(const fs::path& app) {
  if(fs::weakly_canonical(app)!=fs::weakly_canonical(destination()))return;
  const auto script=L"$bihuaTarget=[IO.Path]::GetFullPath("+psquote(app.wstring())+L");$bihuaExpected=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'BihuaWeasel/0.6.44';if($bihuaTarget -ne [IO.Path]::GetFullPath($bihuaExpected)){exit};Wait-Process -Id "+std::to_wstring(GetCurrentProcessId())+L" -ErrorAction SilentlyContinue;$r=Get-Content -LiteralPath (Join-Path $bihuaTarget 'user-install.json') -Raw|ConvertFrom-Json;if($r.status -ne 'uninstalled'){exit};for($i=0;$i -lt 8;$i++){try{Remove-Item -LiteralPath $bihuaTarget -Recurse -Force -ErrorAction Stop;break}catch{Start-Sleep -Seconds 2}}";
  std::wstring cmd=quote(powershell().wstring())+L" -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "+quote(script);
  STARTUPINFOW start{sizeof(start)};start.dwFlags=STARTF_USESHOWWINDOW;start.wShowWindow=SW_HIDE;PROCESS_INFORMATION process{};
  if(CreateProcessW(powershell().c_str(),cmd.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,nullptr,&start,&process)){CloseHandle(process.hThread);CloseHandle(process.hProcess);}
}
static void extract(const fs::path& target) {
#ifndef BIHUA_UNINSTALL
  diagnostics.Step(L"准备安装目录");diagnostics.Write(L"Destination: "+target.wstring()+L"\r\n");
  fs::create_directories(target.parent_path());
  auto resource=FindResourceW(nullptr,L"PAYLOAD",RT_RCDATA);
  if(!resource)throw BihuaSetup::Failure(L"安装包中缺少 PAYLOAD 资源。请重新下载安装包。");
  auto bytes=LockResource(LoadResource(nullptr,resource));const DWORD length=SizeofResource(nullptr,resource);
  GUID id{};CoCreateGuid(&id);wchar_t name[48]{};StringFromGUID2(id,name,48);
  const auto zip=target.parent_path()/(std::wstring(L"bihua-payload-")+name+L".zip");
  const auto script_path=target.parent_path()/(std::wstring(L"bihua-extract-")+name+L".ps1");
  auto extractor=FindResourceW(nullptr,L"EXTRACTOR",RT_RCDATA);
  if(!extractor)throw BihuaSetup::Failure(L"安装包中缺少解包程序。");
  auto script_bytes=LockResource(LoadResource(nullptr,extractor));const DWORD script_length=SizeofResource(nullptr,extractor);
  {std::ofstream file(zip,std::ios::binary);file.write(static_cast<const char*>(bytes),length);if(!file)throw std::runtime_error("Cannot write payload");}
  // Windows PowerShell 5.1 needs a BOM for a UTF-8 script containing Chinese.
  {std::ofstream file(script_path,std::ios::binary);file.write("\xef\xbb\xbf",3);file.write(static_cast<const char*>(script_bytes),script_length);if(!file)throw std::runtime_error("Cannot write extractor");}
  diagnostics.Step(L"解包并校验安装文件");
  const DWORD result=execute(powershell(),L"-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "+quote(script_path.wstring())+L" -Archive "+quote(zip.wstring())+L" -Destination "+quote(target.wstring())+L" -Fingerprint "+hash_bytes(bytes,length)+L" -Version 0.6.44");
  std::error_code cleanup;fs::remove(zip,cleanup);fs::remove(script_path,cleanup);
  if(result)throw BihuaSetup::Failure(L"解包程序返回 "+BihuaSetup::Hex(result)+L"。\r\n"+diagnostics.OutputTail());
  diagnostics.Step(L"完成解包与校验");
#endif
}
static DWORD install(const fs::path& target,bool validation) {
  SetupLock product(validation ? L"" : product_mutex,retry_product);
  SetupLock directory(destination_lock_name(target),retry_destination);
  extract(target);
  diagnostics.Step(validation?L"验证运行环境":L"启动安装运行环境并配置输入法");
  const auto result=execute(target/L"python/python.exe",L"-X utf8 -u -B "+quote((target/L"scripts/Install-Release.py").wstring())+(validation?L" validate":L" install"));
  if(result)throw BihuaSetup::Failure(L"安装步骤返回 "+BihuaSetup::Hex(result)+L"。\r\n"+diagnostics.OutputTail());
  return result;
}
static LRESULT CALLBACK procedure(HWND hwnd,UINT message,WPARAM wp,LPARAM lp) {
  if(message==WM_COMMAND&&LOWORD(wp)==100) {
    if(finished){DestroyWindow(hwnd);return 0;}
    if(working)return 0;
    working=true;EnableWindow(button,FALSE);SetWindowTextW(status,L"正在安装，请稍候…");
    std::thread([hwnd]{DWORD result=1;try{result=install(destination(),false);}catch(const BihuaSetup::Failure& error){last_error=diagnostics.Report(error.detail);}catch(const std::exception& error){last_error=diagnostics.Report(BihuaSetup::Wide(error.what()));}catch(...){last_error=diagnostics.Report(L"发生未知错误。");}PostMessageW(hwnd,WM_APP+1,result,0);}).detach();return 0;
  }
  if(message==WM_APP+1) {
    finished=true;working=false;EnableWindow(button,TRUE);SetWindowTextW(button,L"完成");
    if(wp==0)SetWindowTextW(status,L"安装完成。已打开的软件需重新打开后生效。\n也可保存工作后注销并重新登录 Windows。");
    else {SetWindowTextW(status,L"安装未完成。请复制错误信息以便排查。");EnableWindow(GetDlgItem(hwnd,101),TRUE);ShowWindow(GetDlgItem(hwnd,101),SW_SHOW);MessageBoxW(hwnd,last_error.c_str(),L"笔画输入法安装",MB_ICONERROR);}
    return 0;
  }
  if(message==WM_COMMAND&&LOWORD(wp)==101){
    if(!OpenClipboard(hwnd))return 0;
    auto data=GlobalAlloc(GMEM_MOVEABLE,(last_error.size()+1)*sizeof(wchar_t));
    if(data){auto buffer=GlobalLock(data);if(buffer){memcpy(buffer,last_error.c_str(),(last_error.size()+1)*sizeof(wchar_t));GlobalUnlock(data);EmptyClipboard();if(SetClipboardData(CF_UNICODETEXT,data))data=nullptr;}if(data)GlobalFree(data);}
    CloseClipboard();return 0;
  }
  if(message==WM_CLOSE){if(!working)DestroyWindow(hwnd);return 0;}
  if(message==WM_DESTROY){PostQuitMessage(0);return 0;}
  return DefWindowProcW(hwnd,message,wp,lp);
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE,PWSTR,int) {
  SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
  int argc=0;LPWSTR* argv=CommandLineToArgvW(GetCommandLineW(),&argc);
  try {
    wchar_t self[32768]{};GetModuleFileNameW(nullptr,self,32768);diagnostics.Begin(fs::path(self));
#ifdef BIHUA_UNINSTALL
    if(MessageBoxW(nullptr,L"卸载笔画输入法？\n\n个人词库和学习记录会保留。",L"卸载笔画输入法",MB_OKCANCEL|MB_ICONQUESTION)!=IDOK)return 0;
    SetupLock product(product_mutex,retry_product);
    diagnostics.Step(L"卸载输入法");
    auto app=own_directory();DWORD result=execute(app/L"python/python.exe",L"-X utf8 -u -B "+quote((app/L"scripts/Install-Release.py").wstring())+L" uninstall");
    if(!result){MessageBoxW(nullptr,L"已卸载。个人词库和共享输入法组件已保留。",L"笔画输入法",MB_OK);cleanup_after_exit(app);}
    else MessageBoxW(nullptr,diagnostics.Report(L"卸载步骤返回 "+BihuaSetup::Hex(result)+L"。\r\n"+diagnostics.OutputTail()).c_str(),L"笔画输入法",MB_ICONERROR);
    return static_cast<int>(result);
#else
    if(argc==2&&!wcscmp(argv[1],L"/install"))return static_cast<int>(install(destination(),false));
    if(argc==3&&!wcscmp(argv[1],L"/validate"))return static_cast<int>(install(fs::path(argv[2]),true));
    if(argc==3&&!wcscmp(argv[1],L"/extract-only")){
      const fs::path target(argv[2]);
      SetupLock directory(destination_lock_name(target),retry_destination);
      extract(target);
      return 0;
    }
    WNDCLASSW cls{};cls.lpfnWndProc=procedure;cls.hInstance=instance;cls.hCursor=LoadCursor(nullptr,IDC_ARROW);cls.hbrBackground=reinterpret_cast<HBRUSH>(COLOR_WINDOW+1);cls.lpszClassName=L"BihuaInstaller";RegisterClassW(&cls);
    const double scale=GetDpiForSystem()/96.0;
    window=CreateWindowW(cls.lpszClassName,L"安装笔画输入法 0.6.44 测试版",WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX,100,100,static_cast<int>(610*scale),static_cast<int>(350*scale),nullptr,nullptr,instance,nullptr);
    HFONT font=CreateFontW(-static_cast<int>(17*scale),0,0,0,400,0,0,0,DEFAULT_CHARSET,0,0,ANTIALIASED_QUALITY,0,L"Microsoft YaHei UI");
    auto child=[&](LPCWSTR type,LPCWSTR text,int x,int y,int width,int height,int id,DWORD style){auto h=CreateWindowW(type,text,WS_CHILD|WS_VISIBLE|style,static_cast<int>(x*scale),static_cast<int>(y*scale),static_cast<int>(width*scale),static_cast<int>(height*scale),window,reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),instance,nullptr);SendMessageW(h,WM_SETFONT,reinterpret_cast<WPARAM>(font),TRUE);return h;};
    child(L"STATIC",L"笔画输入法",30,24,540,30,1,0);
    child(L"STATIC",L"五键输入 · 分词与通配 · 本地联想 · 自定义键位",30,72,540,30,2,0);
    child(L"STATIC",L"开源码表测试版。无需另装 Python 或小狼毫。\n首次安装可能需要管理员确认。个人词库不会被覆盖。",30,116,540,65,3,0);
    status=child(L"STATIC",L"准备安装到本机用户目录。",30,196,540,45,4,0);
    button=child(L"BUTTON",L"安装",420,254,145,38,100,WS_TABSTOP|BS_DEFPUSHBUTTON);
    auto copy=child(L"BUTTON",L"复制错误信息",230,254,170,38,101,WS_TABSTOP);ShowWindow(copy,SW_HIDE);EnableWindow(copy,FALSE);
    ShowWindow(window,SW_SHOW);MSG msg{};while(GetMessageW(&msg,nullptr,0,0)>0){if(!IsDialogMessageW(window,&msg)){TranslateMessage(&msg);DispatchMessageW(&msg);}}
    DeleteObject(font);LocalFree(argv);return 0;
#endif
  }catch(const BihuaSetup::Failure& error){auto detail=diagnostics.Report(error.detail);if(argc<=1)MessageBoxW(nullptr,detail.c_str(),L"笔画输入法",MB_ICONERROR);return 1;}
  catch(const std::exception& error){auto detail=diagnostics.Report(BihuaSetup::Wide(error.what()));if(argc<=1)MessageBoxW(nullptr,detail.c_str(),L"笔画输入法",MB_ICONERROR);return 1;}
  catch(...){auto detail=diagnostics.Report(L"安装程序发生未知错误。");if(argc<=1)MessageBoxW(nullptr,detail.c_str(),L"笔画输入法",MB_ICONERROR);return 1;}
}
