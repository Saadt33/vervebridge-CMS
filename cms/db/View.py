#!/usr/bin/python
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
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

"""Views-related database interface for SQLAlchemy. Not to be used
directly (import from SQLAlchemyAll).

"""

from sqlalchemy import Column, ForeignKey, UniqueConstraint, \
     Integer, Float
from sqlalchemy.orm import relationship, backref
from sqlalchemy.orm.collections import mapped_collection

from cms.db.SQLAlchemyUtils import Base
from cms.db.Contest import Contest
from cms.db.User import User
from cms.db.Task import Task


class RankingView(Base):
    """Class to store the current ranking of a contest. Not to be used
    directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'rankingviews'

    # Auto increment primary key.
    id = Column(Integer, primary_key=True)

    # Contest (id and object) the ranking refers to.
    contest_id = Column(Integer,
                        ForeignKey(Contest.id,
                                   onupdate="CASCADE", ondelete="CASCADE"),
                        nullable=False,
                        index=True)
    contest = relationship(
        Contest,
        backref=backref("ranking_view",
                        uselist=False,
                        single_parent=True,
                        cascade="all, delete, delete-orphan"),
        single_parent=True)

    # Time the ranking was made.
    timestamp = Column(Integer, nullable=False)

    # Follows the description of the fields automatically added by
    # SQLAlchemy.
    # scores (dict of (user.username, task.num) to Score objects)

    def __init__(self, contest=None, timestamp=0.0, scores=None):
        self.contest = contest
        self.timestamp = timestamp
        self.scores = scores if scores is not None else {}

    def export_to_dict(self):
        """Return object data as a dictionary.

        """
        return {'timestamp': self.timestamp,
                'scores':    [score.export_to_dict()
                              for score in self.scores.itervalues()]}

    @classmethod
    def import_from_dict(cls, data, tasks_by_name, users):
        """Build the object using data from a dictionary.

        """
        data['scores'] = [Score.import_from_dict(score_data,
                                                 tasks_by_name=tasks_by_name,
                                                 users=users)
                          for score_data in data['scores']]
        data['scores'] = dict([(Score.rankingview_keyfunc(score), score)
                               for score in data['scores']])
        return cls(**data)

    def set_score(self, score):
        """Assign the score to this ranking view. Used to create an
        empty ranking.

        score (object): the Score instance to assign

        """
        score.rankingview = self
        self.scores[(score.user.username, score.task.num)] = score


class Score(Base):
    """Class to store the score a user got in a task. Not to be used
    directly (import it from SQLAlchemyAll).

    """
    __tablename__ = 'scores'
    __table_args__ = (
        UniqueConstraint('rankingview_id', 'task_id', "user_id",
                         name='cst_scores_rankingview_id_task_id_user_id'),
        )

    rankingview_keyfunc = lambda s: (s.user.username, s.task.num)

    # Auto increment primary key.
    id = Column(Integer, primary_key=True)

    # RankingView (id and object) owning the score.
    rankingview_id = Column(Integer,
                            ForeignKey(RankingView.id,
                                       onupdate="CASCADE", ondelete="CASCADE"),
                            nullable=False,
                            index=True)
    rankingview = relationship(
        RankingView,
        backref=backref("scores",
                        collection_class=mapped_collection(
                            rankingview_keyfunc),
                        single_parent=True,
                        cascade="all, delete, delete-orphan"))

    # Task (id and object) the score refers to.
    task_id = Column(Integer,
                     ForeignKey(Task.id,
                                onupdate="CASCADE", ondelete="CASCADE"),
                     nullable=False,
                     index=True)
    task = relationship(Task)

    # User (id and object) owning the score.
    user_id = Column(Integer,
                     ForeignKey(User.id,
                                onupdate="CASCADE", ondelete="CASCADE"),
                     nullable=False,
                     index=True)
    user = relationship(User)

    # The actual score.
    score = Column(Float, nullable=False)

    def __init__(self, score, task=None, user=None, rankingview=None):
        self.score = score
        self.task = task
        self.user = user
        self.rankingview = rankingview

    def export_to_dict(self):
        """Return object data as a dictionary.

        """
        return {'user':  self.user.username,
                'task':  self.task.name,
                'score': self.score}

    @classmethod
    def import_from_dict(cls, data, tasks_by_name, users):
        """Build the object using data from a dictionary.

        """

        def get_user(users, username):
            """Return a user given its username. This is mostly a hack.
            We can't use Contest.get_user() because we don't have the full
            Contest itself, and having it would require even worse hacks.

            """
            for user in users:
                if user.username == username:
                    return user
            raise KeyError("User not found")

        data['task'] = tasks_by_name[data['task']]
        data['user'] = get_user(users, data['user'])
        return cls(**data)
