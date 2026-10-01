"""Read-only LuaJIT 2.0 non-GC64 table navigation for this game build.

Layout reference: https://github.com/LuaJIT/LuaJIT/blob/v2.0/src/lj_obj.h
No remote code injection or game code execution.
"""
import math
import struct

TSTRING = 0xFFFFFFFB
TTABLE = 0xFFFFFFF4


class LuaReader:
    def __init__(self, memory):
        self.memory = memory

    def string(self, address):
        header = self.memory.read(address, 16)
        if len(header) != 16 or header[5] != 4:
            return None
        length = struct.unpack_from('<I', header, 12)[0]
        if length > 256:
            return None
        data = self.memory.read(address + 16, length + 1)
        if len(data) != length + 1 or data[-1] != 0:
            return None
        return data[:-1].decode('utf-8', errors='replace')

    def fields(self, address):
        header = self.memory.read(address, 32)
        if len(header) != 32 or header[5] != 11:
            raise ValueError('Lua table header does not match')
        nodes, mask = struct.unpack_from('<I', header, 20)[0], struct.unpack_from('<I', header, 28)[0]
        if mask > 65535 or (mask & (mask + 1)) or nodes < 65536:
            raise ValueError('Lua table size does not match')
        data = self.memory.read(nodes, (mask + 1) * 24)
        if len(data) != (mask + 1) * 24:
            raise ValueError('Lua table could not be read completely')
        result = {}
        for offset in range(0, len(data), 24):
            key_pointer, key_tag = struct.unpack_from('<II', data, offset + 8)
            if key_tag != TSTRING:
                continue
            key = self.string(key_pointer)
            if key is not None:
                low, tag = struct.unpack_from('<II', data, offset)
                result[key] = {'address': nodes + offset, 'low': low, 'tag': tag,
                               'number': struct.unpack_from('<d', data, offset)[0]}
        return result

    def table(self, address, key):
        value = self.fields(address).get(key)
        if value is None or value['tag'] != TTABLE:
            raise ValueError('Missing table: ' + key)
        return value['low']

    def globals_candidates(self):
        found = set()
        for payload in self.memory.scan_bytes(b'_G\0'):
            pointer = payload - 16
            if self.string(pointer) != '_G':
                continue
            for key_address in self.memory.scan_bytes(struct.pack('<II', pointer, TSTRING)):
                data = self.memory.read(key_address - 8, 8)
                if len(data) != 8:
                    continue
                root, tag = struct.unpack('<II', data)
                if tag != TTABLE:
                    continue
                try:
                    fields = self.fields(root)
                    if fields.get('_G', {}).get('low') == root and all(k in fields for k in ('package', 'pairs', 'type')):
                        found.add(root)
                except ValueError:
                    pass
        return sorted(found)

    def game_store(self, root):
        package = self.table(root, 'package')
        loaded = self.table(package, 'loaded')
        simulation = self.table(loaded, 'klove.simulation')
        store = self.table(simulation, 'store')
        game = self.table(loaded, 'game')
        director = self.table(loaded, 'director')
        if self.table(director, 'active_item') != game:
            raise ValueError('The active screen is not a game level')
        if self.table(game, 'store') != store:
            raise ValueError('Game state references disagree')
        return store

    def gold_at_root(self, root):
        store = self.game_store(root)
        fields = self.fields(store)
        if fields.get('level_init_finished', {}).get('tag') != 0xFFFFFFFD:
            raise ValueError('The level has not finished loading')
        for key, minimum, maximum in [('level_idx', 1, 1000), ('level_mode', 1, 20), ('lives', 0, 1000000), ('player_gold', 0, 10000000)]:
            value = fields.get(key, {}).get('number', float('nan'))
            if not math.isfinite(value) or not minimum <= value <= maximum or not value.is_integer():
                raise ValueError('Current level fields do not match: ' + key)
        return {'root': root, 'store': store, 'address': fields['player_gold']['address'],
                'value': int(fields['player_gold']['number']), 'level': int(fields['level_idx']['number']),
                'paused': fields.get('paused', {}).get('tag') == 0xFFFFFFFD}

    def locate_gold(self):
        cached = getattr(self.memory, '_lua_root', None)
        if cached:
            try:
                return self.gold_at_root(cached)
            except ValueError:
                pass
        matches = []
        for root in self.globals_candidates():
            try:
                matches.append(self.gold_at_root(root))
            except ValueError:
                continue
        if len(matches) != 1:
            raise RuntimeError('无法唯一识别当前关卡，请等待关卡加载完成后重试。')
        self.memory._lua_root = matches[0]['root']
        return matches[0]


def set_gold_auto(memory, value):
    from .core import backup_save, encode_value, log_action, MemoryValueChanged, MemoryReadbackChanged
    encode_value(value, 'double')
    reader = LuaReader(memory)
    first = reader.locate_gold()
    backup = backup_save()
    identity = lambda info: (info['store'], info['address'], info['level'])
    changed_readback = False
    for attempt in range(3):
        current = reader.locate_gold()
        if identity(first) != identity(current):
            raise RuntimeError('关卡正在切换，已停止修改，请加载完成后重试。')
        log_action('auto_gold_write_attempt', pid=memory.pid, level=current['level'], address=hex(current['address']), old=current['value'], new=value, attempt=attempt + 1, backup=str(backup))
        try:
            memory.write_verified(current['address'], current['value'], value, 'double')
        except MemoryValueChanged:
            # Only retry a pre-write mismatch. Never repeatedly overwrite a purchase.
            continue
        except MemoryReadbackChanged:
            changed_readback = True
        break
    else:
        raise RuntimeError('金币连续变化，本次未写入，请稍后再点一次设置。')
    after = reader.locate_gold()
    if identity(after) != identity(current):
        raise RuntimeError('写入后发生了关卡切换，请核对游戏中的金币；没有再次写入。')
    after['requested'] = value
    after['changed_after_write'] = changed_readback or after['value'] != value
    log_action('auto_gold_write_completed', level=after['level'], requested=value, observed=after['value'], changed_after_write=after['changed_after_write'])
    return after
