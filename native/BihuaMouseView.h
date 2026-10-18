#pragma once
#include <algorithm>
#include <cstdint>

// Backend-owned view state. No Rime mutation is needed to move this cursor.
struct BihuaMouseView {
  enum Direction { Left, Right, Up, Down };
  enum Move { NoOp, LocalMove, PageUp, PageDown };
  bool expanded=false;
  bool more=false;
  int navigation=-1, base=0, columns=9, count=0, highlight=0;
  uint32_t generation=0;
  uint64_t projection=0, revision=1;
  int pending_base=-1,pending_column=0,pending_direction=0;
  uint32_t pending_generation=0;
  void PreparePage(int direction,bool restoreNavigation){
    pending_base=base;pending_generation=generation;
    pending_direction=restoreNavigation?direction:0;
    pending_column=navigation>=base?(navigation-base)%columns:0;
  }
  void Sync(uint32_t gen,uint64_t semantic,int first,int n,int size,int selected,bool hasMore=false){
    bool changed=gen!=generation||semantic!=projection||first!=base||size!=count||n!=columns||hasMore!=more;
    bool restore=gen==pending_generation&&pending_direction&&
        first==pending_base+pending_direction*n&&size>0;
    if(gen!=generation||!size)expanded=false;
    if(changed)navigation=-1;
    if(restore){
      int row=pending_direction>0?(size-1)/n:0;
      navigation=first+(std::min)(row*n+pending_column,size-1);
    }
    pending_base=-1;pending_direction=0;
    if(changed)++revision;
    generation=gen;projection=semantic;base=first;columns=n;count=size;more=hasMore;
    highlight=std::clamp(selected,0,(std::max)(0,(std::min)(count,columns)-1));
  }
  void Toggle(){
    if(!expanded&&count<=columns)return;
    expanded=!expanded;
    if(!expanded&&navigation>=base)navigation=base+(navigation-base)%columns;
    ++revision;
  }
  Move Navigate(int direction){
    if(!count||direction<Left||direction>Down)return NoOp;
    int index=navigation>=base&&navigation<base+count?navigation-base:highlight;
    int row=index/columns,col=index%columns;
    if(direction==Left&&col>0)--index;
    if(direction==Right&&col+1<columns&&index+1<count)++index;
    if(direction==Up){
      if(row==0){if(expanded&&base>0)return PageUp;expanded=false;}
      else index-=columns;
    }
    if(direction==Down){
      if(!expanded){if(count>columns)expanded=true;}
      else if((row+1)*columns<count)index=(std::min)(index+columns,count-1);
      else if(more)return PageDown;
    }
    navigation=base+index;++revision;return LocalMove;
  }
  void DisableNavigation(){if(navigation!=-1){navigation=-1;++revision;}}
};
