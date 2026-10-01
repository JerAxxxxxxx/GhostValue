"""Inspect compiled Lua constants without executing the game chunk."""
import ctypes as C
import os
from pathlib import Path
import sys
import zipfile

from ghostvalue.paths import game_executable

GAME = game_executable().parent


def inspect(member, mode='constants'):
    with os.add_dll_directory(str(GAME)):
        lua = C.CDLL(str(GAME / 'lua51.dll'))
    for name, args, result in [
        ('luaL_newstate', [], C.c_void_p), ('luaL_openlibs', [C.c_void_p], None),
        ('luaL_loadbuffer', [C.c_void_p, C.c_char_p, C.c_size_t, C.c_char_p], C.c_int),
        ('lua_setfield', [C.c_void_p, C.c_int, C.c_char_p], None),
        ('luaL_loadstring', [C.c_void_p, C.c_char_p], C.c_int),
        ('lua_pcall', [C.c_void_p, C.c_int, C.c_int, C.c_int], C.c_int),
        ('lua_tolstring', [C.c_void_p, C.c_int, C.POINTER(C.c_size_t)], C.c_void_p),
        ('lua_close', [C.c_void_p], None),
    ]:
        f = getattr(lua, name)
        f.argtypes, f.restype = args, result
    state = lua.luaL_newstate()
    try:
        lua.luaL_openlibs(state)
        with zipfile.ZipFile(GAME / 'Kingdom Rush Genesis.exe') as z:
            data = z.read(member)
        if lua.luaL_loadbuffer(state, data, len(data), member.encode()):
            raise RuntimeError('Could not load game chunk')
        lua.lua_setfield(state, -10002, b'inspected')
        code = r'''
local u=require('jit.util')
local output={}
local function emit(s) output[#output+1]=s end
local function showtable(t,prefix)
 local keys={}
 for k in pairs(t) do keys[#keys+1]=k end
 table.sort(keys,function(a,b) return tostring(a)<tostring(b) end)
 for _,k in ipairs(keys) do
  local v=t[k]
  if type(v)=='table' then showtable(v,prefix..'.'..tostring(k))
  else emit(prefix..'.'..tostring(k)..' = '..tostring(v)) end
 end
end
local function visit(f,path)
 local info=u.funcinfo(f)
 emit('PROTO '..path..' line='..tostring(info.linedefined)..' instructions='..tostring(info.bytecodes))
 for i=0,info.nconsts-1 do emit('N '..i..' '..tostring(u.funck(f,i))) end
 for i=1,info.gcconsts do
  local k=u.funck(f,-i)
  if type(k)=='string' then emit('K '..(-i)..' '..k) end
  if type(k)=='table' then showtable(k,'TABLE '..(-i)) end
 end
 if DISASSEMBLE then
  for pc=1,info.bytecodes-1 do
   local ins,mode=u.funcbc(f,pc)
   emit(string.format('BC %d %08x mode=%x',pc,ins,mode))
  end
 end
 for i=1,info.gcconsts do
  local k=u.funck(f,-i)
  if type(k)=='proto' then visit(k,path..'/'..i) end
 end
end
visit(inspected,'root')
return table.concat(output,'\n')
'''.replace('DISASSEMBLE', 'true' if mode == 'bytecode' else 'false')
        error = lua.luaL_loadstring(state, code.encode()) or lua.lua_pcall(state, 0, 1, 0)
        p = lua.lua_tolstring(state, -1, None)
        result = C.string_at(p).decode('utf-8', errors='replace') if p else ''
        if error:
            raise RuntimeError(result)
        return result
    finally:
        lua.lua_close(state)


if __name__ == '__main__':
    text = inspect(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'constants')
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(text, encoding='utf-8')
    else:
        print(text.encode('ascii', errors='backslashreplace').decode())
