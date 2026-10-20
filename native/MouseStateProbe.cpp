#include "BihuaMouseState.h"
#include <cassert>
#include <iostream>
int main(){
  BihuaMouseState s;
  assert(!s.Queue(0,0,s.generation));
  s.Focus(10);auto first=s.Queue(0,100,s.generation);
  assert(first&&s.Take(10)==first&&!s.Take(20)&&!s.Queue(1,101,s.generation));
  s.Blur(20);assert(s.session==10);
  assert(s.Execute(20,first,110)==-1);
  assert(s.Execute(10,first+1,110)==-1);
  assert(s.Execute(10,first,110)==0);
  assert(s.Execute(10,first,111)==-1);
  assert(!s.Finish(20,first));assert(s.Finish(10,first)&&s.session==10);
  auto expired=s.Queue(5,200,s.generation);assert(s.Execute(10,expired,3201)==-1);
  assert(s.Finish(10,expired)&&s.session==0);
  s.Focus(10);auto old_generation=s.generation;auto old=s.Queue(1,4000,s.generation);s.Focus(20);
  assert(s.Execute(10,old,4001)==-1);
  assert(!s.Queue(2,4002,old_generation));
  auto next=s.Queue(2,4002,s.generation);assert(next&&next!=old);
  s.Blur(10);assert(s.Execute(20,next,4003)==2);assert(s.Finish(20,next));
  assert(!s.Queue(18,4010,s.generation));auto back=s.Queue(17,4011,s.generation);assert(back&&s.Execute(20,back,4012)==17&&s.Finish(20,back));
  auto candidate=s.Queue(BihuaMouseState::Candidate,5000,s.generation,s.projection,36);
  assert(candidate&&s.candidate_index==36);
  s.InvalidateProjection();assert(s.Execute(20,candidate,5001)==-1);
  assert(s.Finish(20,candidate));s.Focus(20);
  assert(!s.Queue(BihuaMouseState::Candidate,5002,s.generation,s.projection-1,36));
  candidate=s.Queue(BihuaMouseState::Candidate,5003,s.generation,s.projection,36);
  assert(s.Execute(20,candidate,5004)==BihuaMouseState::Candidate&&s.candidate_index==36);
  assert(s.Finish(20,candidate));
  for(int action:{BihuaMouseState::Separator,BihuaMouseState::SymbolToggle,BihuaMouseState::SymbolCancel}){
    auto token=s.Queue(action,6000,s.generation,s.projection);assert(token);
    assert(s.Execute(20,token,6001)==action&&s.Execute(20,token,6002)==-1&&s.Finish(20,token));
  }
  assert(!s.Queue(BihuaMouseState::SymbolCancel+1,7000,s.generation));
  std::cout<<"{\"result\":\"PASS\",\"idle_rejects\":true,\"lease_generation\":true,\"late_blur\":true,\"single_inflight\":true,\"at_most_once\":true,\"expiry\":true,\"wrong_session\":true}";
}
