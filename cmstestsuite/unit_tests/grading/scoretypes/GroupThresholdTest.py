#!/usr/bin/env python3

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2018 Stefano Maggiolo <s.maggiolo@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Tests for the GroupThreshold score type."""

from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa
from six import iterkeys

import unittest

from cms.grading.scoretypes.GroupThreshold import GroupThreshold

from cmstestsuite.unit_tests.grading.scoretypes.scoretypetestutils \
    import ScoreTypeTestMixin


class TestGroupThreshold(ScoreTypeTestMixin, unittest.TestCase):
    """Test the GroupThreshold score type."""

    def setUp(self):
        super(TestGroupThreshold, self).setUp()
        self._public_testcases = {
            "1_0": True,
            "1_1": True,
            "2_0": True,
            "2_1": False,
            "3_0": False,
            "3_1": False,
        }

    def test_paramaters_correct(self):
        """Test that correct parameters do not throw."""
        GroupThreshold([], self._public_testcases)
        GroupThreshold([[40, 2, 500], [60.0, 2, 1000]],
                       self._public_testcases)
        GroupThreshold([[40, "1_*", 500.5], [60.0, "2_*", 1000]],
                       self._public_testcases)

    def test_paramaters_invalid_types(self):
        with self.assertRaises(ValueError):
            GroupThreshold([1], self._public_testcases)
        with self.assertRaises(ValueError):
            GroupThreshold(1, self._public_testcases)

    def test_paramaters_invalid_wrong_item_len(self):
        with self.assertRaises(ValueError):
            GroupThreshold([[]], self._public_testcases)
        with self.assertRaises(ValueError):
            GroupThreshold([[1]], self._public_testcases)

    @unittest.skip("Not yet detected.")
    def test_paramaters_invalid_wrong_item_len_not_caught(self):
        with self.assertRaises(ValueError):
            GroupThreshold([[1, 2]], self._public_testcases)

    def test_parameter_invalid_wrong_max_score_type(self):
        with self.assertRaises(ValueError):
            GroupThreshold([["a", 10, 1000]], self._public_testcases)

    def test_parameter_invalid_wrong_testcases_type(self):
        with self.assertRaises(ValueError):
            GroupThreshold([[100, 1j, 1000]], self._public_testcases)

    def test_parameter_invalid_inconsistent_testcases_type(self):
        with self.assertRaises(ValueError):
            GroupThreshold([[40, 10, 500], [40, "1_*", 1000]],
                           self._public_testcases)

    @unittest.skip("Not yet detected.")
    def test_paramaters_invalid_testcases_too_many(self):
        with self.assertRaises(ValueError):
            GroupThreshold([[100, 20, 1000]], self._public_testcases)

    def test_parameter_invalid_testcases_regex_no_match_type(self):
        with self.assertRaises(ValueError):
            GroupThreshold([[100, "9_*", 1000]], self._public_testcases)

    @unittest.skip("Not yet detected.")
    def test_parameter_invalid_wrong_threshold_type_not_caught(self):
        with self.assertRaises(ValueError):
            GroupThreshold([[100, 1, 1000j]], self._public_testcases)

    def test_max_scores_regexp(self):
        """Test max score is correct when groups are regexp-defined."""
        s1, s2, s3 = 10.5, 30.5, 59
        parameters = [[s1, "1_*", 10], [s2, "2_*", 20], [s3, "3_*", 30]]
        header = ["Subtask 1 (10.5)", "Subtask 2 (30.5)", "Subtask 3 (59)"]

        # Only group 1_* is public.
        public_testcases = dict(self._public_testcases)
        self.assertEqual(
            GroupThreshold(parameters, public_testcases).max_scores(),
            (s1 + s2 + s3, s1, header))

        # All groups are public
        for testcase in iterkeys(public_testcases):
            public_testcases[testcase] = True
        self.assertEqual(
            GroupThreshold(parameters, public_testcases).max_scores(),
            (s1 + s2 + s3, s1 + s2 + s3, header))

        # No groups are public
        for testcase in iterkeys(public_testcases):
            public_testcases[testcase] = False
        self.assertEqual(
            GroupThreshold(parameters, public_testcases).max_scores(),
            (s1 + s2 + s3, 0, header))

    def test_max_scores_number(self):
        """Test max score is correct when groups are number-defined."""
        s1, s2, s3 = 10.5, 30.5, 59
        parameters = [[s1, 2, 10], [s2, 2, 20], [s3, 2, 30]]
        header = ["Subtask 1 (10.5)", "Subtask 2 (30.5)", "Subtask 3 (59)"]

        # Only group 1_* is public.
        public_testcases = dict(self._public_testcases)
        self.assertEqual(
            GroupThreshold(parameters, public_testcases).max_scores(),
            (s1 + s2 + s3, s1, header))

        # All groups are public
        for testcase in iterkeys(public_testcases):
            public_testcases[testcase] = True
        self.assertEqual(
            GroupThreshold(parameters, public_testcases).max_scores(),
            (s1 + s2 + s3, s1 + s2 + s3, header))

        # No groups are public
        for testcase in iterkeys(public_testcases):
            public_testcases[testcase] = False
        self.assertEqual(
            GroupThreshold(parameters, public_testcases).max_scores(),
            (s1 + s2 + s3, 0, header))

    def test_compute_score(self):
        s1, s2, s3 = 10.5, 30.5, 59
        parameters = [[s1, "1_*", 10], [s2, "2_*", 20], [s3, "3_*", 30]]
        st = GroupThreshold(parameters, self._public_testcases)
        sr = self.get_submission_result(self._public_testcases)

        # All correct (below threshold).
        for evaluation in sr.evaluations:
            evaluation.outcome = 5.5
        self.assertComputeScore(st.compute_score(sr),
                                s1 + s2 + s3, s1, [s1, s2, s3])

        # Some non-public subtask is incorrect.
        self.set_outcome(sr, "3_1", 100.5)
        self.assertComputeScore(st.compute_score(sr),
                                s1 + s2, s1, [s1, s2, 0])

        # Also the public subtask is incorrect.
        self.set_outcome(sr, "1_0", 12.5)
        self.set_outcome(sr, "1_1", 12.5)
        self.assertComputeScore(st.compute_score(sr),
                                s2, 0.0, [0, s2, 0])

        # Outcome equal to 0 is special and treated as error even if it is
        # below the threshold.
        self.set_outcome(sr, "1_0", 0.0)
        self.set_outcome(sr, "1_1", 0.0)
        self.assertComputeScore(st.compute_score(sr),
                                s2, 0.0, [0, s2, 0])


if __name__ == "__main__":
    unittest.main()
