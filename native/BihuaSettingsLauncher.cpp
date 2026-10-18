#define UNICODE
#define _UNICODE
#include <windows.h>
#include <filesystem>
#include <fstream>
#include <string>
#include <codecvt>

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
  wchar_t executable[32768]{};
  GetModuleFileNameW(nullptr, executable, 32768);
  auto directory = std::filesystem::path(executable).parent_path();
  std::wifstream config(directory / L"settings-script.txt");
  config.imbue(std::locale(config.getloc(), new std::codecvt_utf8<wchar_t>));
  std::wstring script;
  std::getline(config, script);
  if (!std::filesystem::is_regular_file(script)) {
    MessageBoxW(nullptr, L"笔画设置文件不存在，请重新安装设置入口。", L"笔画设置", MB_ICONERROR);
    return 2;
  }
  wchar_t system[32768]{};
  GetSystemDirectoryW(system, 32768);
  auto powershell = std::filesystem::path(system) / L"WindowsPowerShell/v1.0/powershell.exe";
  std::wstring command = L"\"" + powershell.wstring() + L"\" -NoProfile -ExecutionPolicy Bypass -File \"" + script + L"\"";
  STARTUPINFOW startup{sizeof(startup)};
  startup.dwFlags = STARTF_USESHOWWINDOW;
  startup.wShowWindow = SW_HIDE;
  PROCESS_INFORMATION process{};
  if (!CreateProcessW(powershell.c_str(), command.data(), nullptr, nullptr, FALSE,
                      CREATE_NO_WINDOW, nullptr, directory.c_str(), &startup, &process)) return 3;
  WaitForSingleObject(process.hProcess, 15000);
  DWORD result = 1;
  GetExitCodeProcess(process.hProcess, &result);
  CloseHandle(process.hThread); CloseHandle(process.hProcess);
  std::ofstream receipt(directory / L"settings-last-launch.json");
  receipt << "{\"launcher_pid\":" << GetCurrentProcessId() << ",\"exit_code\":" << result << "}";
  if (result != 0 && result != STILL_ACTIVE)
    MessageBoxW(nullptr, L"笔画设置未能启动，请查看设置服务日志。", L"笔画设置", MB_ICONERROR);
  return result == STILL_ACTIVE ? 0 : static_cast<int>(result);
}
