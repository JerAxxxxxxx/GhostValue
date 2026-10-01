import struct
import unittest
from unittest.mock import Mock, patch

from ghostvalue.lua_memory import LuaReader, TSTRING, TTABLE, set_gold_auto
from ghostvalue.core import MemoryValueChanged, MemoryReadbackChanged


class LuaMemoryTests(unittest.TestCase):
    def test_real_layout_reads_named_gold_node(self):
        header = bytearray(32)
        header[5] = 11
        struct.pack_into('<I', header, 20, 0x20000)
        string_header = bytearray(16)
        string_header[5] = 4
        struct.pack_into('<I', string_header, 12, 11)
        pieces = {(0x10000, 32): bytes(header),
                  (0x20000, 24): struct.pack('<dIIII', 870, 0x30000, TSTRING, 0, 0),
                  (0x30000, 16): bytes(string_header),
                  (0x30010, 12): b'player_gold\0'}
        memory = Mock()
        memory.read.side_effect = lambda a, n: pieces.get((a, n), b'')
        field = LuaReader(memory).fields(0x10000)['player_gold']
        self.assertEqual(field['number'], 870)
        self.assertEqual(field['address'], 0x20000)

    def test_invalid_hash_mask_rejected(self):
        header = bytearray(32)
        header[5] = 11
        struct.pack_into('<I', header, 20, 0x20000)
        struct.pack_into('<I', header, 28, 0xffffffff)
        memory = Mock()
        memory.read.return_value = bytes(header)
        with self.assertRaises(ValueError):
            LuaReader(memory).fields(0x10000)

    def test_menu_rejects_stale_game_store(self):
        reader = LuaReader(Mock())
        # package, loaded, simulation, store, game, director, active menu
        with patch.object(reader, 'table', side_effect=[1, 2, 3, 4, 5, 6, 7]):
            with self.assertRaisesRegex(ValueError, 'active screen'):
                reader.game_store(99)

    def test_unpaused_game_can_write(self):
        memory = Mock()
        before = dict(paused=False, store=10, address=20, level=1, value=1000)
        with patch('ghostvalue.lua_memory.LuaReader.locate_gold', side_effect=[before, before, dict(before, value=9999)]), patch('ghostvalue.core.backup_save'), patch('ghostvalue.core.log_action'):
            self.assertEqual(set_gold_auto(memory, 9999)['value'], 9999)
            memory.write_verified.assert_called_once_with(20, 1000, 9999, 'double')

    def test_prewrite_change_retries_with_fresh_value(self):
        memory = Mock()
        memory.write_verified.side_effect = [MemoryValueChanged(), None]
        before = dict(paused=False, store=10, address=20, level=1, value=1000)
        with patch('ghostvalue.lua_memory.LuaReader.locate_gold', side_effect=[before, before, dict(before, value=1010), dict(before, value=9999)]), patch('ghostvalue.core.backup_save') as backup, patch('ghostvalue.core.log_action'):
            set_gold_auto(memory, 9999)
            self.assertEqual(memory.write_verified.call_count, 2)
            memory.write_verified.assert_called_with(20, 1010, 9999, 'double')
            backup.assert_called_once()

    def test_postwrite_purchase_is_not_overwritten(self):
        memory = Mock()
        memory.write_verified.side_effect = MemoryReadbackChanged()
        before = dict(paused=False, store=10, address=20, level=1, value=1000)
        with patch('ghostvalue.lua_memory.LuaReader.locate_gold', side_effect=[before, before, dict(before, value=9869)]), patch('ghostvalue.core.backup_save'), patch('ghostvalue.core.log_action'):
            result = set_gold_auto(memory, 9999)
            self.assertTrue(result['changed_after_write'])
            self.assertEqual(result['value'], 9869)
            memory.write_verified.assert_called_once()

    def test_retries_bounded(self):
        memory = Mock()
        memory.write_verified.side_effect = MemoryValueChanged()
        before = dict(paused=False, store=10, address=20, level=1, value=1000)
        with patch('ghostvalue.lua_memory.LuaReader.locate_gold', return_value=before), patch('ghostvalue.core.backup_save'), patch('ghostvalue.core.log_action'):
            with self.assertRaises(RuntimeError):
                set_gold_auto(memory, 9999)
            self.assertEqual(memory.write_verified.call_count, 3)

    def test_permission_failure_not_retried(self):
        memory = Mock()
        memory.write_verified.side_effect = PermissionError('denied')
        before = dict(paused=False, store=10, address=20, level=1, value=1000)
        with patch('ghostvalue.lua_memory.LuaReader.locate_gold', return_value=before), patch('ghostvalue.core.backup_save'), patch('ghostvalue.core.log_action'):
            with self.assertRaises(PermissionError):
                set_gold_auto(memory, 9999)
            memory.write_verified.assert_called_once()

    def test_level_change_during_backup_cannot_write(self):
        memory = Mock()
        before = dict(paused=True, store=10, address=20, level=1, value=1000)
        after = dict(before, store=30, level=2)
        with patch('ghostvalue.lua_memory.LuaReader.locate_gold', side_effect=[before, after]), patch('ghostvalue.core.backup_save', return_value='test.zip'):
            with self.assertRaises(RuntimeError):
                set_gold_auto(memory, 9999)
            memory.write_verified.assert_not_called()

    def test_writes_freshly_resolved_address_and_value(self):
        memory = Mock()
        before = dict(paused=True, store=10, address=20, level=1, value=870)
        after = dict(before, value=9999)
        with patch('ghostvalue.lua_memory.LuaReader.locate_gold', side_effect=[before, before, after]), patch('ghostvalue.core.backup_save', return_value='test.zip'), patch('ghostvalue.core.log_action'):
            result = set_gold_auto(memory, 9999)
            memory.write_verified.assert_called_once_with(20, 870, 9999, 'double')
            self.assertEqual(result['value'], 9999)


if __name__ == '__main__':
    unittest.main()
