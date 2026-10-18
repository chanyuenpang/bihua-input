#define UNICODE
#define _UNICODE
#include <windows.h>
#include <WeaselIPC.h>
#include <ResponseParser.h>
#include <thread>
#include <vector>
#include <atomic>
#include <iostream>
#include <chrono>
int main(){
  HANDLE stalled=CreateFileW(weasel::GetPipeName().c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,OPEN_EXISTING,0,nullptr);
  if(stalled==INVALID_HANDLE_VALUE)return 2;
  weasel::PipeMessage unknown{static_cast<WEASEL_IPC_COMMAND>(WM_APP+2000),0,0};DWORD written=0;
  if(!WriteFile(stalled,&unknown,sizeof(unknown),&written,nullptr)){CloseHandle(stalled);return 3;}
  // Intentionally never read this connection's reply.
  Sleep(200);
  std::atomic<int> failures{0};auto began=std::chrono::steady_clock::now();
  std::vector<std::thread> threads;
  const int keys[]={'h','s','p','n'};const wchar_t* preedits[]={L"一",L"丨",L"丿",L"丶"};
  for(int i=0;i<4;++i)threads.emplace_back([&,i]{
    for(int n=0;n<3;++n){
      weasel::Client client;weasel::Status status;weasel::Context ctx;weasel::Config cfg;std::wstring commit;
      weasel::ResponseParser parser(&commit,&ctx,&status,&cfg,nullptr);
      if(!client.Connect()){++failures;return;}
      client.StartSession();
      if(!client.GetResponseData(std::ref(parser))||status.schema_id!=L"bihua_mvp"){++failures;return;}
      client.ProcessKeyEvent(weasel::KeyEvent(keys[i],0));ctx=weasel::Context{};
      if(!client.GetResponseData(std::ref(parser))||ctx.preedit.str.find(preedits[i])==std::wstring::npos||!commit.empty())++failures;
      client.ClearComposition();client.EndSession();
    }
  });
  for(auto& thread:threads)thread.join();
  CloseHandle(stalled);
  auto elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-began).count();
  std::cout<<"{\"result\":\""<<(failures?"FAIL":"PASS")<<"\",\"unread_peer_does_not_block\":true,\"parallel_connections\":4,\"isolated_responses\":12,\"failures\":"<<failures<<",\"elapsed_ms\":"<<elapsed<<"}";
  return failures?1:0;
}
