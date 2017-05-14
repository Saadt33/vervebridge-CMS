#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2013 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2015 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2014 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2014 Artem Iglikov <artem.iglikov@gmail.com>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
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

"""Task-related handlers for AWS for a specific contest.

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

from cms.db import Contest, Task
from cmscommon.datetime import make_datetime

from .base import BaseHandler, require_permission


class ContestTasksHandler(BaseHandler):
    REMOVE_FROM_CONTEST = "Remove from contest"
    MOVE_UP = "Move up"
    MOVE_DOWN = "Move down"

    @require_permission(BaseHandler.AUTHENTICATED)
    def get(self, contest_id):
        self.contest = self.safe_get_item(Contest, contest_id)

        self.r_params = self.render_params()
        self.r_params["contest"] = self.contest
        self.r_params["unassigned_tasks"] = \
            self.sql_session.query(Task)\
                .filter(Task.contest == None)\
                .all()  # noqa
        self.render("contest_tasks.html", **self.r_params)

    @require_permission(BaseHandler.PERMISSION_ALL)
    def post(self, contest_id):
        fallback_page = self.make_unprefixed_absolute_href("contest", contest_id, "tasks")

        self.contest = self.safe_get_item(Contest, contest_id)

        try:
            task_id = self.get_argument("task_id")
            operation = self.get_argument("operation")
            assert operation in (
                self.REMOVE_FROM_CONTEST,
                self.MOVE_UP,
                self.MOVE_DOWN
            ), "Please select a valid operation"
        except Exception as error:
            self.application.service.add_notification(
                make_datetime(), "Invalid field(s)", repr(error))
            self.redirect(fallback_page)
            return

        task = self.safe_get_item(Task, task_id)
        task2 = None

        if operation == self.REMOVE_FROM_CONTEST:
            # Save the current task_num (position in the contest).
            task_num = task.num

            # Unassign the task to the contest.
            task.contest = None
            task.num = None  # not strictly necessary

            # Decrease by 1 the num of every subsequent task.
            for t in self.sql_session.query(Task)\
                         .filter(Task.contest == self.contest)\
                         .filter(Task.num > task_num)\
                         .all():
                t.num -= 1

        elif operation == self.MOVE_UP:
            task2 = self.sql_session.query(Task)\
                        .filter(Task.contest == self.contest)\
                        .filter(Task.num == task.num - 1)\
                        .first()

        elif operation == self.MOVE_DOWN:
            task2 = self.sql_session.query(Task)\
                        .filter(Task.contest == self.contest)\
                        .filter(Task.num == task.num + 1)\
                        .first()

        # Swap task.num and task2.num, if needed
        if task2 is not None:
            tmp_a, tmp_b = task.num, task2.num
            task.num, task2.num = None, None
            self.sql_session.flush()
            task.num, task2.num = tmp_b, tmp_a

        if self.try_commit():
            # Create the user on RWS.
            self.application.service.proxy_service.reinitialize()

        # Maybe they'll want to do this again (for another task)
        self.redirect(fallback_page)


class AddContestTaskHandler(BaseHandler):
    @require_permission(BaseHandler.PERMISSION_ALL)
    def post(self, contest_id):
        fallback_page = self.make_unprefixed_absolute_href("contest", contest_id, "tasks")

        self.contest = self.safe_get_item(Contest, contest_id)

        try:
            task_id = self.get_argument("task_id")
            # Check that the admin selected some task.
            assert task_id != "null", "Please select a valid task"
        except Exception as error:
            self.application.service.add_notification(
                make_datetime(), "Invalid field(s)", repr(error))
            self.redirect(fallback_page)
            return

        task = self.safe_get_item(Task, task_id)

        # Assign the task to the contest.
        task.num = len(self.contest.tasks)
        task.contest = self.contest

        if self.try_commit():
            # Create the user on RWS.
            self.application.service.proxy_service.reinitialize()

        # Maybe they'll want to do this again (for another task)
        self.redirect(fallback_page)
