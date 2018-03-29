#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2018 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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

"""Tests for communication functions.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa
import six

import unittest
from datetime import timedelta

# Needs to be first to allow for monkey patching the DB connection string.
from cmstestsuite.unit_tests.databasemixin import DatabaseMixin

from cms.db import Question, Announcement, Message
from cms.server.contest.communication import accept_question, \
    QuestionsNotAllowed, UnacceptableQuestion, get_communications
from cmscommon.datetime import make_datetime, make_timestamp


class TestAcceptQuestion(DatabaseMixin, unittest.TestCase):

    def setUp(self):
        super(TestAcceptQuestion, self).setUp()
        self.timestamp = make_datetime()
        self.contest = self.add_contest(allow_questions=True)
        self.user = self.add_user()
        self.participation = self.add_participation(
            contest=self.contest, user=self.user)

    def call(self, subject, text):
        res = accept_question(self.session, self.participation,
                              self.timestamp, subject, text)
        self.session.commit()
        return res

    def assertQuestionExists(self, question):
        q = self.session.query(Question) \
            .filter(Question.id == question.id)
        self.assertIs(q.first(), question)

    def test_success(self):
        q = self.call("mysubject", "mytext")
        self.assertIsNotNone(q)
        self.assertQuestionExists(q)

    def test_questions_not_allowed(self):
        self.contest.allow_questions = False
        with self.assertRaises(QuestionsNotAllowed):
            self.call("mysubject", "mytext")

    def test_question_too_big(self):
        with self.assertRaises(UnacceptableQuestion):
            self.call("mysubject" + Question.MAX_SUBJECT_LENGTH * ".", "mytext")
        with self.assertRaises(UnacceptableQuestion):
            self.call("mysubject", "mytext" + Question.MAX_TEXT_LENGTH * ".")


class TestGetCommunications(DatabaseMixin, unittest.TestCase):

    def setUp(self):
        super(TestGetCommunications, self).setUp()
        self.timestamp = make_datetime()
        self.contest = self.add_contest()
        self.user = self.add_user()
        self.participation = self.add_participation(
            contest=self.contest, user=self.user)

    def at(self, timestamp):
        return self.timestamp + timedelta(seconds=timestamp)

    def add_announcement(self, subject, text, timestamp, contest=None):
        if contest is None:
            contest = self.contest
        a = Announcement(
            subject=subject, text=text, timestamp=self.at(timestamp),
            contest=contest)
        self.session.add(a)
        d = {"type": "announcement", "subject": subject, "text": text,
             "timestamp": make_timestamp(self.timestamp) + timestamp}
        return d

    def add_message(self, subject, text, timestamp, participation=None):
        if participation is None:
            participation = self.participation
        m = Message(
            subject=subject, text=text, timestamp=self.at(timestamp),
            participation=participation)
        self.session.add(m)
        d = {"type": "message", "subject": subject, "text": text,
             "timestamp": make_timestamp(self.timestamp) + timestamp}
        return d

    def add_question(self, subject, text, timestamp, participation=None):
        if participation is None:
            participation = self.participation
        q = Question(
            subject=subject, text=text, question_timestamp=self.at(timestamp),
            participation=participation)
        self.session.add(q)
        return q

    def set_answer(self, q, subject, text, timestamp):
        q.reply_subject = subject
        q.reply_text = text
        q.reply_timestamp = self.at(timestamp)
        # If subject and/or text are None, "shift the rest up".
        gen = (s for s in [subject, text, "", ""] if s is not None)
        subject, text = next(gen), next(gen)
        d = {"type": "question", "subject": subject, "text": text,
             "timestamp": make_timestamp(self.timestamp) + timestamp}
        return d

    def call(self, timestamp, after=None):
        return get_communications(
            self.session, self.participation, self.at(timestamp),
            after=self.at(after) if after is not None else None)

    def verify(self, ts, test_interval, res):
        for test_time in range(test_interval):
            six.assertCountEqual(
                self, self.call(test_time),
                res if ts <= test_time else [])
        for test_time_after in range(test_interval):
            for test_time_until in range(test_time_after + 1, test_interval):
                six.assertCountEqual(
                    self, self.call(test_time_until, after=test_time_after),
                    res if test_time_after < ts <= test_time_until else [])

    def test_no_elements(self):
        self.assertEqual(self.call(1), [])

    def test_announcement(self):
        ts = 2
        d = self.add_announcement("subject for all", "text for all", ts)
        self.verify(ts, 5, [d])

    def test_message(self):
        ts = 2
        d = self.add_message("subject for you", "text for you", ts)
        self.verify(ts, 5, [d])

    def test_question(self):
        q_ts = 2
        q = self.add_question("question for admins", "text for admins", q_ts)
        self.verify(q_ts, 5, [])

        a_ts = 5
        d = self.set_answer(q, "subject for you", "text for you", a_ts)
        self.verify(a_ts, 8, [d])

        # Test some of subject and text being None.
        d = self.set_answer(q, None, "text for you", a_ts)
        self.verify(a_ts, 8, [d])
        d = self.set_answer(q, "subject for you", None, a_ts)
        self.verify(a_ts, 8, [d])
        d = self.set_answer(q, None, None, a_ts)
        self.verify(a_ts, 8, [d])

    def test_all_together(self):
        ts = 2
        a_d = self.add_announcement("subject for all", "text for all", ts)
        m_d = self.add_message("subject for you", "text for you", ts)
        q = self.add_question("question for admins", "text for admins", ts)
        self.verify(ts, 5, [a_d, m_d])

        q_d = self.set_answer(q, "subject for you", "text for you", ts)
        self.verify(ts, 5, [a_d, m_d, q_d])


if __name__ == "__main__":
    unittest.main()
