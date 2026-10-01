import ctypes as C
import json
import os
import unittest
import zipfile

from ghostvalue.permanent_patch import GAME, MANIFEST, MAP, SETTINGS, wrappers


@unittest.skipUnless(MANIFEST.exists(), "Requires a local game and prepared permanent-patch backup")
class WrapperTests(unittest.TestCase):
    def setUp(self):
        with os.add_dll_directory(str(GAME.parent)):
            self.lua = C.CDLL(str(GAME.parent / 'lua51.dll'))
        for name, args, result in [
            ('luaL_newstate', [], C.c_void_p), ('luaL_openlibs', [C.c_void_p], None),
            ('luaL_loadbuffer', [C.c_void_p, C.c_char_p, C.c_size_t, C.c_char_p], C.c_int),
            ('lua_setfield', [C.c_void_p, C.c_int, C.c_char_p], None),
            ('luaL_loadstring', [C.c_void_p, C.c_char_p], C.c_int),
            ('lua_pcall', [C.c_void_p, C.c_int, C.c_int, C.c_int], C.c_int),
            ('lua_tolstring', [C.c_void_p, C.c_int, C.c_void_p], C.c_void_p),
            ('lua_close', [C.c_void_p], None),
        ]:
            f = getattr(self.lua, name)
            f.argtypes, f.restype = args, result
        self.state = self.lua.luaL_newstate()
        self.lua.luaL_openlibs(self.state)
        self.manifest = json.loads(MANIFEST.read_text())

    def tearDown(self):
        self.lua.lua_close(self.state)

    def load(self, name, data):
        self.assertEqual(self.lua.luaL_loadbuffer(self.state, data, len(data), name.encode()), 0)
        self.lua.lua_setfield(self.state, -10002, name.encode())

    def run_lua(self, script):
        code = self.lua.luaL_loadstring(self.state, script.encode()) or self.lua.lua_pcall(self.state, 0, 0, 0)
        if code:
            p = self.lua.lua_tolstring(self.state, -1, None)
            self.fail(C.string_at(p).decode(errors='replace') if p else 'Lua error')

    def test_actual_settings_module_gains_allowances_without_xp_changes(self):
        with zipfile.ZipFile(self.manifest['backup']) as z:
            self.load('original_settings', z.read(SETTINGS))
        self.load('patched_settings', wrappers(self.manifest['profile'])[SETTINGS])
        self.run_lua('''
DIFFICULTY_EASY=1; DIFFICULTY_NORMAL=2; DIFFICULTY_HARD=3; DIFFICULTY_IMPOSSIBLE=4
DAMAGE_TRUE=1; DAMAGE_MAGICAL=2; DAMAGE_PHYSICAL=3; DAMAGE_EXPLOSION=4; DAMAGE_ELECTRICAL=5
GAME_MODE_IRON=3; GAME_MODE_NO_HEROES=4; GAME_MODE_EXTRA_HEROES=5; GAME_MODE_BLITZ=6; GAME_MODE_KR1=7
KR_TARGET="desktop"
require=function(name) assert(name=="features", name); return {} end
love={filesystem={load=function(path)
 assert(path=="ghostvalue_original/game_settings.lua"); return original_settings
end}}
local base=original_settings()
local modified=patched_settings()
assert(modified.upgrades_points_per_stage[1]==100)
assert(modified.upgrades_points_per_stage[6]==120)
assert(modified.skill_points_for_hero_level[1]==110)
assert(modified.skill_points_for_hero_level[10]==146)
for i,v in ipairs(base.hero_xp_thresholds) do assert(modified.hero_xp_thresholds[i]==v) end
for i,v in ipairs(base.powers_xp_thresholds) do assert(modified.powers_xp_thresholds[i]==v) end
-- A fresh game startup must not add the bonus twice.
local next_start=patched_settings()
assert(next_start.skill_points_for_hero_level[1]==110)
''')

    def test_spell_wrapper_preserves_stats_and_applies_after_reset(self):
        self.load('patched_map', wrappers(self.manifest['profile'])[MAP])
        self.run_lua('''
love={filesystem={load=function(path)
 assert(path=="ghostvalue_original/kviews_screen_map_game.lua")
 return function()
  PowerRoomView={get_unit_stats=function(self)
   return {remaining_points=self.level-1-self.spent,xp=321,level=self.level}
  end}
  return "original module result"
 end
end}}
assert(patched_map()=="original module result")
local self={level=3,spent=0}
local stats=PowerRoomView.get_unit_stats(self)
assert(stats.remaining_points==12 and stats.xp==321 and stats.level==3)
self.spent=1; assert(PowerRoomView.get_unit_stats(self).remaining_points==11)
self.spent=0; assert(PowerRoomView.get_unit_stats(self).remaining_points==12)
patched_map(); assert(PowerRoomView.get_unit_stats(self).remaining_points==12)
''')


if __name__ == '__main__':
    unittest.main()
