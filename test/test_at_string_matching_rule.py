#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from unittest import TestCase
import serial
from at_cmd_client import AtStringMatchingRule, AtCommandClient


class Test(TestCase):

    def setUp(self) -> None:
        self.client = AtCommandClient(
            name=__name__,
            uart_handle=serial.Serial()
        )

    def test_at_string_matching_rule_exact_true(self):
        self.assertTrue(self.client.match_string("OK", "OK", AtStringMatchingRule.Exact))

    def test_at_string_matching_rule_exact_at_end(self):
        self.assertTrue(self.client.match_string("OK", "Before OK\r\n", AtStringMatchingRule.Exact))

    def test_at_string_matching_rule_exact_at_start(self):
        self.assertTrue(self.client.match_string("OK", "OK After\r\n", AtStringMatchingRule.Exact))

    def test_at_string_matching_rule_exact_at_substring(self):
        self.assertTrue(self.client.match_string("OK", "Before OK After\r\n", AtStringMatchingRule.Exact))

    def test_at_string_matching_rule_exact_newline(self):
        self.assertTrue(self.client.match_string("OK", "OK\r\n", AtStringMatchingRule.Exact))

    def test_at_string_matching_rule_exact_different_case(self):
        self.assertFalse(self.client.match_string("ok", "OK\r\n", AtStringMatchingRule.Exact))


if __name__ == '__main__':
    pass
