import struct
import unittest
from unittest.mock import patch
import ghostvalue.core as core


class MemoryTests(unittest.TestCase):
    def test_stale_value_never_opens_write_handle(self):
        memory = object.__new__(core.Memory)
        memory.pid = 1
        with patch.object(memory, 'alive', return_value=True), patch.object(memory, 'read', return_value=struct.pack('<d', 869)), patch.object(core.kernel, 'OpenProcess') as open_process:
            with self.assertRaises(RuntimeError):
                memory.write_verified(1234, 870, 9999, 'double')
            open_process.assert_not_called()

    def test_wrong_size_never_opens_write_handle(self):
        memory = object.__new__(core.Memory)
        with patch.object(core.kernel, 'OpenProcess') as open_process:
            with self.assertRaises(ValueError):
                memory.write_block_verified(1234, b'ab', b'abc')
            open_process.assert_not_called()

    def test_ambiguous_budget_refused(self):
        memory = object.__new__(core.Memory)
        memory.pid = -1
        with patch.object(memory, 'scan_bytes', return_value=[100, 200]):
            with self.assertRaises(RuntimeError):
                core.locate_budget(memory, 'hero')

    def test_budget_write_includes_every_expected_entry(self):
        memory = object.__new__(core.Memory)
        values = core.BUDGETS['hero'][:]
        with patch.object(core, 'locate_budget', return_value=(1234, values)), patch.object(core, 'backup_save', return_value='test.zip'), patch.object(core, 'log_action'), patch.object(memory, 'write_block_verified', side_effect=RuntimeError('simulated write failure')) as write:
            with self.assertRaises(RuntimeError):
                core.add_budget(memory, 'hero', 10)
            write.assert_called_once_with(1234, core.pack_budget(values), core.pack_budget([v + 10 for v in values]))
        self.assertEqual(values, core.BUDGETS['hero'])

    def test_invalid_bonus_does_not_back_up_or_write(self):
        for amount in [-1, 0, 101, 1.5]:
            with patch.object(core, 'locate_budget') as locate:
                with self.assertRaises(ValueError):
                    core.add_budget(None, 'hero', amount)
                locate.assert_not_called()

    def test_gold_zero_and_types(self):
        self.assertEqual(core.encode_value(0, 'double'), b'\0' * 8)
        self.assertEqual(core.encode_value(9999, 'int32'), struct.pack('<i', 9999))
        with self.assertRaises(ValueError):
            core.encode_value(1, 'unknown')


if __name__ == '__main__':
    unittest.main()
