"""Version-checked spell allowance constant; leaves XP and levels unchanged."""
import hashlib
import math
import struct

from .core import backup_save, log_action
from .lua_memory import LuaReader

# Populated from the inspected 1.00.052 PowerRoomView.get_unit_stats body.
BODY_HASH = '1775a25f47f9d23b7fc54ece45fbd29daff93d59f1ba434ae18467bbb419d24f'


def locate_spell_budget(memory):
    if not memory.alive():
        raise RuntimeError('游戏已经退出，请重新连接')
    reader = LuaReader(memory)
    root = getattr(memory, '_lua_root', None)
    roots = [root] if root else reader.globals_candidates()
    matches = []
    for root in roots:
        try:
            methods = reader.table(reader.table(root, 'PowerRoomView'), '__instanceDict')
            field = reader.fields(methods).get('get_unit_stats', {})
            if field.get('tag') != 0xFFFFFFF7:
                continue
            closure = memory.read(field['low'], 20)
            if len(closure) != 20 or closure[5] != 8 or closure[6] != 0:
                continue
            pc = struct.unpack_from('<I', closure, 16)[0]
            proto = memory.read(pc - 64, 64)
            if len(proto) != 64 or proto[5] != 7:
                continue
            sizebc, constants, ngc, nn = (struct.unpack_from('<I', proto, offset)[0] for offset in (8, 16, 24, 28))
            trace = struct.unpack_from('<H', proto, 38)[0]
            if (sizebc, ngc, nn) != (208, 62, 1) or trace != 0:
                continue
            source = reader.string(struct.unpack_from('<I', proto, 40)[0])
            if source != '@./kr6/kviews_screen_map_game.lua':
                continue
            body = memory.read(pc + 4, (sizebc - 1) * 4)
            if hashlib.sha256(body).hexdigest() != BODY_HASH:
                continue
            key_ref = memory.read(constants - 59 * 4, 4)
            if len(key_ref) != 4 or reader.string(struct.unpack('<I', key_ref)[0]) != 'remaining_points':
                continue
            raw = memory.read(constants, 8)
            if len(raw) != 8:
                continue
            baseline = struct.unpack('<d', raw)[0]
            if not math.isfinite(baseline) or not baseline.is_integer() or not -1000000 <= baseline <= 1:
                continue
            matches.append({'root': root, 'address': constants, 'baseline': baseline, 'bonus': int(1 - baseline)})
        except ValueError:
            continue
    if len(matches) != 1:
        raise RuntimeError('法术计算模块与当前适配版本不匹配，或已被即时编译。请重启游戏后重试；已停止写入。')
    memory._lua_root = matches[0]['root']
    return matches[0]


def add_spell_budget(memory, amount):
    if not isinstance(amount, int) or not 1 <= amount <= 100:
        raise ValueError('每次请输入 1 到 100 点')
    first = locate_spell_budget(memory)
    updated = first['baseline'] - amount
    if updated < -1000000:
        raise ValueError('额度超过原型支持范围')
    backup = backup_save()
    current = locate_spell_budget(memory)
    if first != current:
        raise RuntimeError('法术状态在备份期间发生变化，请重试')
    log_action('spell_budget_attempt', old_bonus=first['bonus'], new_bonus=first['bonus'] + amount, backup=str(backup))
    memory.write_block_verified(first['address'], struct.pack('<d', first['baseline']), struct.pack('<d', updated))
    log_action('spell_budget_readback_verified', new_bonus=first['bonus'] + amount)
    return backup
