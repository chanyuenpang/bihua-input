-- Exposure is the current Rime menu page, not proof that a person read it.
local M, Episode = {}, {}
Episode.__index = Episode
function M.new(rows, page_size)
  return setmetatable({rows=rows, page_size=page_size or 9, visible={}, seen={}, closed=false},Episode)
end
function Episode:expose(page)
  if self.closed or page<0 or page%1~=0 then return end
  for index=page*self.page_size+1,math.min((page+1)*self.page_size,#self.rows) do
    local row=self.rows[index]
    self:note(row)
  end
end
function Episode:note(row)
  if not self.closed and row and not self.seen[row.id] then
    self.seen[row.id]=true;self.visible[#self.visible+1]=row
  end
end
function Episode:close()
  if self.closed then return nil end
  self.closed=true;return self.visible
end
function Episode:abandon() self.closed=true;self.visible={} end
return M
