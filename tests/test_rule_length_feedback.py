"""Agent rule proposals over the length limit are refused out loud, not silently truncated."""
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mcp_bridge
from rules import MAX_REASON_CHARS, MAX_TEXT_CHARS, RuleStore
from store import MessageStore


class RuleLengthFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        tmp_path = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.rules = RuleStore(str(tmp_path / 'rules.json'))
        self.messages = MessageStore(str(tmp_path / 'messages.jsonl'))
        self.stack.enter_context(patch.object(mcp_bridge, 'rules', self.rules))
        self.stack.enter_context(patch.object(mcp_bridge, 'store', self.messages))
        self.stack.enter_context(patch.object(mcp_bridge, 'registry', None))

    def propose(self, rule, reason=''):
        return mcp_bridge.chat_rules(action='propose', sender='ben', rule=rule, reason=reason)

    def assert_nothing_saved(self):
        assert self.rules.list_all() == []
        assert self.messages.get_recent(50) == []

    def test_text_over_limit_is_refused_with_numbers(self):
        result = self.propose('x' * (MAX_TEXT_CHARS + 1))
        assert result.startswith('Error:')
        assert f'{MAX_TEXT_CHARS + 1} chars' in result
        assert f'limit is {MAX_TEXT_CHARS}' in result
        assert 'Shorten it by 1' in result
        self.assert_nothing_saved()

    def test_text_at_limit_is_saved_whole(self):
        text = 'y' * MAX_TEXT_CHARS
        result = self.propose(text)
        assert result.startswith('Proposed rule #')
        assert self.rules.list_all()[0]['text'] == text

    def test_reason_over_limit_is_refused_with_numbers(self):
        result = self.propose('Short rule', reason='r' * (MAX_REASON_CHARS + 5))
        assert result.startswith('Error: reason is')
        assert f'limit is {MAX_REASON_CHARS}' in result
        assert 'Shorten it by 5' in result
        self.assert_nothing_saved()

    def test_edge_whitespace_does_not_count(self):
        text = 'z' * MAX_TEXT_CHARS
        assert self.propose(f'  {text}\n').startswith('Proposed rule #')
        assert self.rules.list_all()[0]['text'] == text

    def test_accents_count_as_characters_not_bytes(self):
        text = 'é' * MAX_TEXT_CHARS
        assert self.propose(text).startswith('Proposed rule #')
        assert self.rules.list_all()[0]['text'] == text

    def test_instructions_announce_real_limit(self):
        assert f'max {MAX_TEXT_CHARS} chars' in mcp_bridge._MCP_INSTRUCTIONS
        assert 'max 160 chars' not in mcp_bridge._MCP_INSTRUCTIONS


if __name__ == '__main__':
    unittest.main()
