#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

"""Tests for the ImportContest script"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa
import six

import unittest

# Needs to be first to allow for monkey patching the DB connection string.
from cmstestsuite.unit_tests.testdbgenerator import TestCaseWithDatabase

from cms.db import Contest, SessionGen, Submission

from cmscontrib.loaders.base_loader import ContestLoader, TaskLoader
from cmscontrib.ImportContest import ContestImporter


def fake_loader_factory(contest, contest_has_changed=False,
                        tasks=None, usernames=None):
    """Return a Loader class always returning the same information

    contest (Contest): the contest to return
    contest_has_changed (bool): what to return from contest_has_changed
    tasks ([(string, bool)]): list of task names and whether they have changed
    usernames ([string]): list of usernames of participations

    """

    tasks = tasks if tasks is not None else []
    usernames = usernames if usernames is not None else []

    task_name_list = [t.name for t, has_changed in tasks]
    tasks_by_name = dict((t.name, {
        "task": t,
        "has_changed": has_changed
    }) for t, has_changed in tasks)
    participations = [{"username": u} for u in usernames]

    class FakeLoader(ContestLoader):
        @staticmethod
        def detect(path):
            return True

        def get_contest(self):
            return contest, task_name_list, participations

        def contest_has_changed(self):
            return contest_has_changed

        def get_task_loader(self, taskname):

            class FakeTaskLoader(TaskLoader):
                @staticmethod
                def detect(path):
                    return True

                def get_task(self, get_statement):
                    return tasks_by_name.get(taskname, None)["task"]

                def task_has_changed(self):
                    return tasks_by_name.get(taskname, None)["has_changed"]

            return FakeTaskLoader(self.path, self.file_cacher)

    return FakeLoader


class TestImportContest(TestCaseWithDatabase):

    def setUp(self):
        super(TestImportContest, self).setUp()

        # DB already contains a contest in a contest with a submission.
        self.contest = self.add_contest()
        self.participation = self.add_participation(contest=self.contest)
        self.task = self.add_task(contest=self.contest)
        self.dataset = self.add_dataset(task=self.task)
        self.task.active_dataset = self.task.datasets[0]
        self.submission = self.add_submission(self.task, self.participation)

        self.session.commit()
        self.contest_id = self.contest.id
        self.name = self.contest.name
        self.description = self.contest.description
        self.task_id = self.task.id
        self.task_title = self.task.title
        self.task_name = self.task.name
        self.dataset_id = self.dataset.id
        self.dataset_description = self.dataset.description
        self.submission_id = self.submission.id
        self.username = self.participation.user.username
        self.last_name = self.participation.user.last_name

    def tearDown(self):
        self.delete_data()
        super(TestImportContest, self).tearDown()

    @staticmethod
    def do_import(contest, tasks, participations,
                  contest_has_changed=False, update_contest=False,
                  import_tasks=False, update_tasks=False):
        """Create an importer and call do_import in a convenient way"""
        return ContestImporter(
            "path", False, import_tasks, update_contest, update_tasks, False,
            fake_loader_factory(contest, contest_has_changed,
                                tasks, participations)).do_import()

    def assertContestInDb(self, name, description, task_names_and_titles,
                          usernames_and_last_names):
        """Assert that the contest with the given data is in the DB

        The query is done by contest name, and to avoid caching, we query from
        a brand new session.

        From contest_id on, parameters are checked only if not None.

        """
        with SessionGen() as session:
            db_contests = session.query(Contest) \
                .filter(Contest.name == name).all()
            self.assertEqual(len(db_contests), 1)
            c = db_contests[0]
            self.assertEqual(c.name, name)
            self.assertEqual(c.description, description)
            six.assertCountEqual(self, [(t.name, t.title) for t in c.tasks],
                                 task_names_and_titles)
            six.assertCountEqual(self, [(u.user.username, u.user.last_name)
                                        for u in c.participations],
                                 usernames_and_last_names)

    def assertSubmissionCount(self, count):
        """Assert that we have that many submissions in the DB"""
        with SessionGen() as session:
            self.assertEqual(session.query(Submission).count(), count)

    def test_import_task_in_db_not_attached(self):
        # Completely new contest, the task is already in the DB, not attached
        # to any contest. The import should succeed and the task should made
        # part of the contest.
        task_name = "new_task_name"
        task_title = "new_task_title"
        task = self.add_task(name=task_name, title=task_title, contest=None)
        self.session.commit()
        name = "new_name"
        description = "new_desc"
        contest = self.get_contest(name=name, description=description)
        ret = self.do_import(contest, [(task, True)], [], import_tasks=False)

        self.assertTrue(ret)
        self.assertContestInDb(name, description,
                               [(task_name, task_title)],
                               [])

    def test_import_task_not_in_db_imported(self):
        # Completely new contest, the task is not in the DB, but we ask to
        # import it. The import should succeed and the task should made part of
        # the contest.
        name = "new_name"
        description = "new_desc"
        contest = self.get_contest(name=name, description=description)
        task_name = "new_task_name"
        task_title = "new_task_title"
        task = self.get_task(name=task_name, title=task_title, contest=contest)
        ret = self.do_import(contest, [(task, True)], [], import_tasks=True)

        self.assertTrue(ret)
        self.assertContestInDb(name, description,
                               [(task_name, task_title)],
                               [])

    def test_import_task_not_in_db_fail(self):
        # Completely new contest, but the task is not in the DB and we do not
        # ask to import it, so import should fail.
        name = "new_name"
        description = "new_desc"
        contest = self.get_contest(name=name, description=description)
        task_name = "new_task_name"
        task_title = "new_task_title"
        task = self.get_task(name=task_name, title=task_title, contest=contest)
        ret = self.do_import(contest, [(task, True)], [], import_tasks=False)

        self.assertFalse(ret)

    def test_import_task_in_db_already_attached_fail(self):
        # Completely new contest, but the task is already attached to another
        # contest in the DB.
        name = "new_name"
        description = "new_desc"
        contest = self.get_contest(name=name, description=description)
        task = self.get_task(name=self.task_name, title=self.task_title,
                             contest=contest)
        ret = self.do_import(contest, [(task, True)], [],
                             import_tasks=True, update_tasks=True)

        self.assertFalse(ret)
        # Task still tied to the original contest.
        self.assertContestInDb(self.name, self.description,
                               [(self.task_name, self.task_title)],
                               [(self.username, self.last_name)])

    def test_contest_exists_fail(self):
        # Contest exists but we do not ask to update it, should fail.
        description = "new_desc"
        contest = self.get_contest(name=self.name, description=description)
        ret = self.do_import(contest, [], [], update_contest=False)

        self.assertFalse(ret)
        self.assertContestInDb(self.name, self.description,
                               [(self.task_name, self.task_title)],
                               [(self.username, self.last_name)])

    def test_update_contest(self):
        # Update the existing contest, task not updated, participations should
        # not change even if we do not pass any.
        description = "new_desc"
        contest = self.get_contest(name=self.name, description=description)
        task_title = "new_task_title"
        task = self.get_task(name=self.task_name, title=task_title,
                             contest=contest)
        ret = self.do_import(contest, [(task, True)], [],
                             contest_has_changed=True, update_contest=True,
                             import_tasks=False, update_tasks=False)

        self.assertTrue(ret)
        self.assertContestInDb(self.name, description,
                               [(self.task_name, self.task_title)],
                               [(self.username, self.last_name)])
        self.assertSubmissionCount(1)

    def test_update_contest_removing_task(self):
        # Update the existing contest, the existing task is untied, but we
        # keep the submission.
        description = "new_desc"
        contest = self.get_contest(name=self.name, description=description)
        ret = self.do_import(contest, [], [],
                             contest_has_changed=True, update_contest=True,
                             import_tasks=True, update_tasks=True)

        self.assertTrue(ret)
        self.assertContestInDb(self.name, description, [],
                               [(self.username, self.last_name)])
        self.assertSubmissionCount(1)

    def test_update_contest_updating_and_adding_task(self):
        # Update the existing contest and the task, also add a new one.
        description = "new_desc"
        contest = self.get_contest(name=self.name, description=description)
        task_title = "new_task_title"
        task = self.get_task(name=self.task_name, title=task_title,
                             contest=contest)
        new_task_name = "new_task_name"
        new_task_title = "new_task_title"
        new_task = self.get_task(name=new_task_name, title=new_task_title,
                                 contest=contest)
        ret = self.do_import(contest, [(task, True), (new_task, True)], [],
                             contest_has_changed=True, update_contest=True,
                             import_tasks=True, update_tasks=True)

        self.assertTrue(ret)
        self.assertContestInDb(self.name, description,
                               [(self.task_name, task_title),
                                (new_task_name, new_task_title)],
                               [(self.username, self.last_name)])
        self.assertSubmissionCount(1)

    def test_import_participation_in_db(self):
        # Completely new contest, no tasks, a new participation for an existing
        # user, whose existing submission should be retained.
        name = "new_name"
        description = "new_desc"
        contest = self.get_contest(name=name, description=description)
        ret = self.do_import(contest, [], [self.username])

        self.assertTrue(ret)
        self.assertContestInDb(name, description,
                               [],
                               [(self.username, self.last_name)])
        self.assertSubmissionCount(1)

    def test_import_participation_not_in_db(self):
        # Completely new contest, no tasks, a new participation but the user
        # is not in the DB, so it should fail.
        name = "new_name"
        description = "new_desc"
        contest = self.get_contest(name=name, description=description)
        username = "new_username"
        ret = self.do_import(contest, [], [username])

        self.assertFalse(ret)
        self.assertSubmissionCount(1)

    def test_update_contest_same_participations(self):
        # Update the existing contest, task not updated, participations passed.
        description = "new_desc"
        contest = self.get_contest(name=self.name, description=description)
        task_title = "new_task_title"
        task = self.get_task(name=self.task_name, title=task_title,
                             contest=contest)
        ret = self.do_import(contest, [(task, True)], [self.username],
                             contest_has_changed=True, update_contest=True,
                             import_tasks=False, update_tasks=False)

        self.assertTrue(ret)
        self.assertContestInDb(self.name, description,
                               [(self.task_name, self.task_title)],
                               [(self.username, self.last_name)])
        self.assertSubmissionCount(1)


if __name__ == "__main__":
    unittest.main()
