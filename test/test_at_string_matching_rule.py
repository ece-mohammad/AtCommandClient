#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from unittest import TestCase

from at_cmd_client import AtString, AtStringMatchingRule


class Test(TestCase):

    def test_at_string_matching_rule_exact_true(self):
        self.assertEqual(
            AtString.match_string("OK", "OK", AtStringMatchingRule.Exact),
            "OK",
        )

    def test_at_string_matching_rule_exact_at_end(self):
        self.assertEqual(
            AtString.match_string("OK", "Before OK", AtStringMatchingRule.Exact),
            "OK",
        )

    def test_at_string_matching_rule_exact_at_start(self):
        self.assertEqual(
            AtString.match_string("OK", "OK After", AtStringMatchingRule.Exact),
            "OK",
        )

    def test_at_string_matching_rule_exact_at_substring(self):
        self.assertEqual(
            AtString.match_string("OK", "Before OK After", AtStringMatchingRule.Exact),
            "OK",
        )

    def test_at_string_matching_rule_exact_newline(self):
        self.assertEqual(
            AtString.match_string("OK", "OK\r\n", AtStringMatchingRule.Exact),
            "OK",
        )

    def test_at_string_matching_rule_exact_different_case(self):
        self.assertEqual(
            AtString.match_string("OK", "ok", AtStringMatchingRule.Exact),
            "",
        )

    def test_at_string_matching_rule_regex_string(self):
        self.assertEqual(
            AtString.match_string("OK", "OK", AtStringMatchingRule.Regex),
            "OK",
        )

    def test_at_string_matching_rule_regex_pattern_true(self):
        self.assertEqual(
            AtString.match_string("\\w{2}", "OK", AtStringMatchingRule.Regex),
            "OK",
        )

    def test_at_string_matching_rule_regex_pattern_false(self):
        self.assertEqual(
            AtString.match_string("[a-zA-Z]{2}", "12", AtStringMatchingRule.Regex),
            "",
        )

    def test_at_string_matching_rule_regex_value_pattern(self):
        self.assertEqual(
            AtString.match_string("\\+CME ERROR:\\s*\\d*", "+CME ERROR: 53", AtStringMatchingRule.Regex),
            "+CME ERROR: 53",
        )
