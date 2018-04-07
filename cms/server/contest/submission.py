#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2014 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2017 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2018 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2013 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2014 Artem Iglikov <artem.iglikov@gmail.com>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
# Copyright © 2015-2016 William Di Luigi <williamdiluigi@gmail.com>
# Copyright © 2016 Myungwoo Chun <mc.tamaki@gmail.com>
# Copyright © 2016 Amir Keivan Mohtashami <akmohtashami97@gmail.com>
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

"""Submission-related handlers for CWS for a specific task.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa

import logging

from sqlalchemy import func, desc

from cms.db import Submission, Task


logger = logging.getLogger(__name__)


def get_submission_count(
        sql_session, participation, contest=None, task=None, cls=Submission):
    """Return the amount of submissions the contestant sent in.

    Count the submissions (or user tests) for the given participation
    on the given task or contest (that is, on all the contest's tasks).

    sql_session (Session): the SQLAlchemy session to use.
    participation (Participation): the participation to fetch data for.
    contest (Contest|None): if given count on all the contest's tasks.
    task (Task|None): if given count only on this task (trumps contest).
    cls (Submission|UserTest): if the UserTest class is given, count
        user tests rather than submissions.

    return (int): the count.

    """
    q = sql_session.query(func.count(cls.id))
    if task is not None:
        if contest is not None and task.contest is not contest:
            raise ValueError("contest and task don't match")
        q = q.filter(cls.task == task)
    elif contest is not None:
        q = q.join(cls.task) \
            .filter(Task.contest == contest)
    else:
        raise ValueError("need at least one of contest and task")
    q = q.filter(cls.participation == participation)
    return q.scalar()


def check_max_number(
        sql_session, max_number, participation, contest=None, task=None,
        cls=Submission):
    """Check whether user already sent in given number of submissions.

    Verify whether the given participation did already hit the given
    constraint on the maximum number of submissions (i.e., whether they
    submitted at least as many submissions as the limit) and return the
    *opposite*, that is, return whether they are allowed to send more.

    sql_session (Session): the SQLAlchemy session to use.
    max_number (int|None): the constraint; None means no constraint has
        to be enforced and thus True is always returned.
    participation (Participation): the participation to fetch data for.
    contest (Contest|None): if given count on all the contest's tasks.
    task (Task|None): if given count only on this task (trumps contest).
    cls (Submission|UserTest): if the UserTest class is given, count
        user tests rather than submissions.

    return (bool): whether the contestant can submit more.

    """
    if max_number is None or participation.unrestricted:
        return True
    count = get_submission_count(
        sql_session, participation, contest=contest, task=task, cls=cls)
    if count >= max_number:
        return False
    return True


def get_latest_submission(
        sql_session, participation, contest=None, task=None, cls=Submission):
    """Return the most recent submission the contestant sent in.

    Retrieve the submission (or user test) with the latest timestamp
    among the ones for the given participation on the given task or
    contest (that is, on all the contest's tasks).

    sql_session (Session): the SQLAlchemy session to use.
    participation (Participation): the participation to fetch data for.
    contest (Contest|None): if given look at all the contest's tasks.
    task (Task|None): if given look only at this task (trumps contest).
    cls (Submission|UserTest): if the UserTest class is given, fetch
        user tests rather than submissions.

    return (Submission|UserTest|None): the latest submission/user test,
        if any.

    """
    q = sql_session.query(cls)
    if task is not None:
        if contest is not None and task.contest is not contest:
            raise ValueError("contest and task don't match")
        q = q.filter(cls.task == task)
    elif contest is not None:
        q = q.join(cls.task) \
            .filter(Task.contest == contest)
    else:
        raise ValueError("need at least one of contest and task")
    q = q.filter(cls.participation == participation) \
        .order_by(desc(cls.timestamp))
    return q.first()


def check_min_interval(
        sql_session, min_interval, timestamp, participation, contest=None,
        task=None, cls=Submission):
    """Check whether user sent in latest submission long enough ago.

    Verify whether at least the given amount of time has passed since
    the given participation last sent in a submission (or user test).

    sql_session (Session): the SQLAlchemy session to use.
    min_interval (timedelta|None): the constraint; None means no
        constraint has to be enforced and thus True is always returned.
    timestamp (datetime): the current timestamp.
    participation (Participation): the participation to fetch data for.
    contest (Contest|None): if given look at all the contest's tasks.
    task (Task|None): if given look only at this task (trumps contest).
    cls (Submission|UserTest): if the UserTest class is given, fetch
        user tests rather than submissions.

    return (bool): whether the contestant's "cool down" period has
        expired and they can submit again.

    """
    if min_interval is None or participation.unrestricted:
        return True
    submission = get_latest_submission(
        sql_session, participation, contest=contest, task=task, cls=cls)
    if submission is not None \
            and (timestamp - submission.timestamp < min_interval):
        return False
    return True
