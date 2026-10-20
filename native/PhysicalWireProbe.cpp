#define UNICODE
#define _UNICODE
#include <windows.h>
#include <WeaselIPC.h>
#include <PipeChannel.h>
#include <cassert>
#include <thread>
#include <iostream>
#include <vector>
class Receiver:public weasel::PipeChannel<DWORD,weasel::PipeMessage>{
 public:
  Receiver(std::wstring name):PipeChannel(std::move(name)){}
  void Read(HANDLE pipe,weasel::PipeMessage& msg){_Receive(pipe,&msg,sizeof(msg));}
  void Reply(HANDLE pipe,DWORD value){DWORD size=0;assert(WriteFile(pipe,&value,sizeof(value),&size,nullptr)&&size==sizeof(value));}
};
class Sender:public weasel::PipeChannel<weasel::PipeMessage>{
 public:Sender(std::wstring name):PipeChannel(std::move(name)){}
 HANDLE Handle()const{return hpipe;}
};
int main(){
  std::wstring name=L"\\\\.\\pipe\\BihuaPhysicalWireProbe-"+std::to_wstring(GetCurrentProcessId())+L"-"+std::to_wstring(GetTickCount64());
  HANDLE pipe=CreateNamedPipeW(name.c_str(),PIPE_ACCESS_DUPLEX,PIPE_TYPE_MESSAGE|PIPE_READMODE_MESSAGE|PIPE_WAIT,1,65536,65536,0,nullptr);
  assert(pipe!=INVALID_HANDLE_VALUE);
  int requests=0;
  std::thread worker([&]{
    BOOL connected=ConnectNamedPipe(pipe,nullptr);assert(connected||GetLastError()==ERROR_PIPE_CONNECTED);
    Receiver receive(name);
    for(int i=0;i<6;++i){
      weasel::PipeMessage msg{};receive.Read(pipe,msg);++requests;
      if(receive.ReceivedBodyBytes()<sizeof(BihuaPhysicalEventV1)||msg.wParam!=sizeof(BihuaPhysicalEventV1)){receive.Reply(pipe,0);continue;}
      BihuaPhysicalEventV1 event{};memcpy(&event,receive.ReceivedPayload(),sizeof(event));
      bool valid=event.Valid()&&event.vk==0xff&&event.scan==0x63&&event.flags==1&&event.rime==0&&event.repeat==1;
      receive.Reply(pipe,valid?1:0);
    }
  });
  Sender sender(name);assert(sender.Connect());HANDLE client=sender.Handle();
  DWORD mode=PIPE_READMODE_MESSAGE;assert(SetNamedPipeHandleState(client,&mode,nullptr,nullptr));
  BihuaPhysicalEventV1 event;event.vk=0xff;event.scan=0x63;event.flags=1;
  sender.WritePayload(&event,sizeof(event));weasel::PipeMessage header{WEASEL_IPC_PHYSICAL_KEY,sizeof(event),42};
  assert(sender.Transact(header)==1);
  auto request=[&](const void* data,size_t length,DWORD declared){
    weasel::PipeMessage header{WEASEL_IPC_PHYSICAL_KEY,declared,42};std::vector<char> bytes(sizeof(header)+length);
    memcpy(bytes.data(),&header,sizeof(header));if(length)memcpy(bytes.data()+sizeof(header),data,length);
    DWORD count=0,result=999;assert(WriteFile(client,bytes.data(),static_cast<DWORD>(bytes.size()),&count,nullptr));
    assert(ReadFile(client,&result,sizeof(result),&count,nullptr)&&count==sizeof(result));return result;
  };
  assert(request(&event,sizeof(event),sizeof(event))==1);
  assert(request(&event,13,sizeof(event))==0);
  assert(request(nullptr,0,sizeof(event))==0);
  event.version=2;assert(request(&event,sizeof(event),sizeof(event))==0);
  event.version=1;assert(request(&event,sizeof(event),12)==0);
  worker.join();sender.Disconnect();DisconnectNamedPipe(pipe);CloseHandle(pipe);assert(requests==6);
  std::cout<<"{\"result\":\"PASS\",\"actual_named_pipe\":true,\"unknown_vk_scan_roundtrip\":true,\"short_body_rejected\":true,\"no_body_rejected\":true,\"version_and_size_rejected\":true,\"production_pipe_buffer\":true,\"system_input_modified\":false}"<<std::endl;
}
