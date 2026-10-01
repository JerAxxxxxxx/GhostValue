import struct
import unittest
from unittest.mock import Mock, patch

from ghostvalue.spell_budget import add_spell_budget, locate_spell_budget


class SpellBudgetTests(unittest.TestCase):
    def test_zero_point_spell_receives_bonus_without_xp_write(self):
        memory = Mock()
        state = dict(root=1, address=1234, baseline=1.0, bonus=0)
        with patch('ghostvalue.spell_budget.locate_spell_budget', return_value=state), patch('ghostvalue.spell_budget.backup_save', return_value='test.zip'), patch('ghostvalue.spell_budget.log_action'):
            add_spell_budget(memory, 10)
            memory.write_block_verified.assert_called_once_with(1234, struct.pack('<d', 1), struct.pack('<d', -9))

    def test_repeated_bonus_accumulates(self):
        memory = Mock()
        state = dict(root=1, address=1234, baseline=-9.0, bonus=10)
        with patch('ghostvalue.spell_budget.locate_spell_budget', return_value=state), patch('ghostvalue.spell_budget.backup_save', return_value='test.zip'), patch('ghostvalue.spell_budget.log_action'):
            add_spell_budget(memory, 5)
            memory.write_block_verified.assert_called_once_with(1234, struct.pack('<d', -9), struct.pack('<d', -14))

    def test_changed_function_after_backup_refuses_write(self):
        memory = Mock()
        state = dict(root=1, address=1234, baseline=1.0, bonus=0)
        with patch('ghostvalue.spell_budget.locate_spell_budget', side_effect=[state, dict(state, address=5678)]), patch('ghostvalue.spell_budget.backup_save', return_value='test.zip'):
            with self.assertRaises(RuntimeError):
                add_spell_budget(memory, 10)
            memory.write_block_verified.assert_not_called()

    def test_exited_process_refuses_lookup(self):
        memory = Mock()
        memory.alive.return_value = False
        with self.assertRaises(RuntimeError):
            locate_spell_budget(memory)
        memory.read.assert_not_called()

    def test_invalid_amount_refuses_lookup(self):
        for amount in [0, -10, 101, 1.5]:
            with patch('ghostvalue.spell_budget.locate_spell_budget') as locate:
                with self.assertRaises(ValueError):
                    add_spell_budget(None, amount)
                locate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
