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

"""Scoring service. Its jobs is to handle everything is about
assigning scores and communicating them to the world.

In particular, it takes care of handling the internal way of keeping
the score (i.e., the ranking view) and send to the external ranking
services the scores, via http requests.

"""

import httplib
import simplejson as json
import base64

from cms import config, default_argument_parser, logger
from cms.async import ServiceCoord
from cms.async.AsyncLibrary import Service, rpc_method
from cms.db import ask_for_contest
from cms.db.SQLAlchemyAll import SessionGen, Submission, Contest
from cms.grading.scoretypes import get_score_type
from cms.service import get_submissions


class CannotSendError(Exception):
    pass


def get_authorization(username, password):
    """Compute the basic authentication string needed to send data to
    the ranking.

    username (string): username to login with.
    password (string): password of the username.
    return (string): the basic auth header, or ValueError if username
                     contains ":"

    """
    if ":" in username:
        raise ValueError("Colon `:' is not allowed in a username.")
    return "Basic %s" % base64.b64encode(username + ':' + password)


def encode_id(entity_id):
    """Encode the id using only A-Za-z0-9_.

    entity_id (string): the entity id to encode.
    return (string): encoded entity id.

    """
    encoded_id = ""
    for char in str(entity_id):
        if char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" \
               "abcdefghijklmnopqrstuvwxyz" \
               "0123456789":
            try:
                encoded_id += "_" + hex(ord(char))[-2:]
            except TypeError:
                logger.error("Entity %s cannot be send correctly, "
                             "sending anyway (this may cause errors)." %
                             entity_id)
        else:
            encoded_id += char
    return encoded_id


def post_data(connection, url, data, auth, method="POST"):
    """Send some data to url through the connection using username and
    password specified in auth.

    connection (httplib.HTTPConnection): the connection.
    url (string): the relative url.
    auth (string): the authorization as returned by get_authorization.
    data (dict): the data to json-encode and send.
    return (int): status of the http request.

    """
    connection.request(method,
                       url,
                       json.dumps(data),
                       {'Authorization': auth})
    res = connection.getresponse()
    res.read()
    return res.status


def put_data(connection, url, data, auth):
    """See post_data.

    """
    return post_data(connection, url, data, auth, "PUT")


def safe_post_data(connection, url, data, auth, operation):
    """Call post_data issuing a warning if we get a status different
    from 200 or 201. See post_data for parameters.

    """
    try:
        status = post_data(connection, url, data, auth)
    except Exception as error:
        status = repr(error)
    if status not in [200, 201]:
        logger.info("Status %s while %s to ranking." %
                    (status, operation))
        raise CannotSendError


def safe_put_data(connection, url, data, auth, operation):
    """Call put_data issuing a warning if we get a status different
    from 200 or 201. See post_data for parameters.

    """
    try:
        status = put_data(connection, url, data, auth)
    except Exception as error:
        status = repr(error)
    if status not in [200, 201]:
        logger.info("Status %s while %s to ranking." %
                    (status, operation))
        raise CannotSendError


def send_submission(ranking, submission_url, submission_put_data):
    """Send a submission to the remote ranking.

    ranking ((string, string)): address and authorization string of
                                ranking server.
    submission_url (string): relative url in the remote ranking.
    submission_put_data (dict): dictionary to send to the ranking to
                                send the submission.

    return (bool): success of operation.

    """
    logger.info("Posting new submission %s." % submission_url)
    connection = httplib.HTTPConnection(ranking[0])
    auth = ranking[1]
    safe_put_data(connection, submission_url, submission_put_data, auth,
                  "sending submission %s" % submission_url)


def send_change(ranking, subchange_url, subchange_put_data):
    """Send a change to a submission (token or score update).

    ranking ((string, string)): address and authorization string of
                                ranking server.
    subchange_url (string): relative url in the remote ranking.
    subchange_put_data (dict): dictionary to send to the ranking to
                               update the submission.

    return (bool): success of operation.

    """
    logger.info("Posting change %s for submission %s." %
                (subchange_url, subchange_put_data["submission"]))
    connection = httplib.HTTPConnection(ranking[0])
    auth = ranking[1]
    safe_put_data(connection, subchange_url, subchange_put_data, auth,
                  "sending change %s" % subchange_url)


class ScoringService(Service):
    """Scoring service.

    """

    # How often we try to send data to remote rankings.
    CHECK_DISPATCH_TIME = 5.0

    # How often we look for submission not scored/tokened.
    JOBS_NOT_DONE_CHECK_TIME = 347.0

    def __init__(self, shard, contest_id):
        logger.initialize(ServiceCoord("ScoringService", shard))
        Service.__init__(self, shard, custom_logger=logger)

        self.contest_id = contest_id

        self.scorers = {}
        self._initialize_scorers()

        # If for some reason (SS switched off for a while, or broken
        # connection with ES), submissions have been left without
        # score, this is the list where you want to pur their
        # ids. Note that list != [] if and only if there is an alive
        # timeout for the method "score_old_submission".
        self.submission_ids_to_score = []
        self.submission_ids_to_token = []

        # We need to load every submission at start, but we don't want
        # to invalidate every score so that we can simply load the
        # score-less submissions. So we keep a set of submissions that
        # we analyzed (for scoring and for tokens).
        self.submission_ids_scored = set()
        self.submission_ids_tokened = set()

        # Initialize ranking web servers we need to send data to.
        self.rankings = []
        for i in xrange(len(config.rankings_address)):
            address = config.rankings_address[i]
            username = config.rankings_username[i]
            password = config.rankings_password[i]
            auth = get_authorization(username, password)
            self.rankings.append(("%s:%d" % tuple(address), auth))
        self.operation_queue = []

        for ranking in self.rankings:
            self.operation_queue.append((self.initialize, [ranking]))

        self.add_timeout(self.dispatch_operations, None,
                         ScoringService.CHECK_DISPATCH_TIME,
                         immediately=True)
        self.add_timeout(self.search_jobs_not_done, None,
                         ScoringService.JOBS_NOT_DONE_CHECK_TIME,
                         immediately=True)

    def _initialize_scorers(self):
        """Initialize scorers, the ScoreType objects holding all
        submissions for a given task and deciding scores, and create
        an empty ranking view for the contest.

        """
        with SessionGen(commit=False) as session:
            contest = session.query(Contest).\
                      filter_by(id=self.contest_id).first()
            logger.info("(Re)creating ranking view for contest `%s'" %
                        contest.name)
            contest.create_empty_ranking_view(timestamp=contest.start)
            for task in contest.tasks:
                self.scorers[task.id] = get_score_type(task=task)
            session.commit()

    def search_jobs_not_done(self):
        """Look in the database for submissions that have not been
        scored for no good reasons. Put the missing job in the queue.

        """
        with SessionGen(commit=False) as session:
            contest = session.query(Contest).\
                      filter_by(id=self.contest_id).first()

            new_submission_ids_to_score = []
            new_submission_ids_to_token = []
            for submission in contest.get_submissions():
                if submission.evaluated() and \
                        submission.id not in self.submission_ids_scored:
                    new_submission_ids_to_score.append(submission.id)
                if submission.tokened() and \
                        submission.id not in self.submission_ids_tokened:
                    new_submission_ids_to_token.append(
                        (submission.id, submission.token.timestamp))

        new_s = len(new_submission_ids_to_score)
        old_s = len(self.submission_ids_to_score)
        new_t = len(new_submission_ids_to_token)
        old_t = len(self.submission_ids_to_token)
        logger.info("Submissions found to score/token: %d, %d." %
                    (new_s, new_t))
        if new_s + new_t > 0:
            self.submission_ids_to_score = new_submission_ids_to_score + \
                                           self.submission_ids_to_score
            self.submission_ids_to_token = new_submission_ids_to_token + \
                                           self.submission_ids_to_token
            if old_s + old_t == 0:
                self.add_timeout(self.score_old_submissions, None,
                                 0.5, immediately=False)

        # Run forever.
        return True

    def score_old_submissions(self):
        """The submissions in the submission_ids_to_score list are
        evaluated submissions that we can assign a score to, and this
        method scores a bunch of these at a time. This method keeps
        getting called while the list is non-empty. (Exactly the same
        happens for the submissions to token.)

        Note: doing this way (instead of putting everything in the
        __init__) prevent freezing the service at the beginning in the
        case of many old submissions.

        """
        to_score = len(self.submission_ids_to_score)
        to_token = len(self.submission_ids_to_token)
        to_score_now = to_score if to_score < 4 else 4
        to_token_now = to_token if to_token < 16 else 16
        logger.info("Old submission yet to score/token: %s/%s." %
                    (to_score, to_token))

        for unused_i in xrange(to_score_now):
            self.new_evaluation(self.submission_ids_to_score[-1])
            del self.submission_ids_to_score[-1]
        if to_score - to_score_now > 0:
            return True

        for unused_i in xrange(to_token_now):
            self.submission_tokened(self.submission_ids_to_token[-1][0],
                                    self.submission_ids_to_token[-1][1])
            del self.submission_ids_to_token[-1]
        if to_token - to_token_now > 0:
            return True

        logger.info("Finished loading old submissions.")
        return False

    def dispatch_operations(self):
        """Look at the operations still to do in the queue and tries
        to dispatch them

        """
        pending = len(self.operation_queue)
        if pending > 0:
            logger.info("%s operations still pending." % pending)

        failed_rankings = set([])
        new_queue = []
        for method, args in self.operation_queue:
            if args[0] in failed_rankings:
                new_queue.append((method, args))
                continue
            try:
                method(*args)
            except:
                logger.info("Ranking %s not connected or generic error." %
                            args[0][0])
                new_queue.append((method, args))
                failed_rankings.add(args[0])
        self.operation_queue = new_queue

        # We want this to run forever.
        return True

    def initialize(self, ranking):
        """Send to the ranking all the data that are supposed to be
        sent before the contest: contest, users, tasks. No support for
        teams, flags and faces.

        ranking ((string, string)): address and authorization string
                                    of ranking server.
        return (bool): success of operation

        """
        logger.info("Initializing rankings.")
        connection = httplib.HTTPConnection(ranking[0])
        auth = ranking[1]

        with SessionGen(commit=False) as session:
            contest = Contest.get_from_id(self.contest_id, session)
            if contest is None:
                logger.error("Received request for unexistent contest id %s." %
                             self.contest_id)
                raise KeyError
            contest_name = contest.name
            contest_url = "/contests/%s" % encode_id(contest_name)
            contest_data = {"name": contest.description,
                            "begin": contest.start,
                            "end": contest.stop}

            users = dict((encode_id(user.username),
                          {"f_name": user.first_name,
                           "l_name": user.last_name,
                           "team": None})
                         for user in contest.users
                         if not user.hidden)

            tasks = dict((encode_id(task.name),
                          {"name": task.title,
                           "contest": encode_id(contest.name),
                           "max_score": 100.0,
                           "extra_headers": [],
                           "order": task.num,
                           "short_name": encode_id(task.name)})
                         for task in contest.tasks)

        safe_put_data(connection, contest_url, contest_data, auth,
                      "sending contest %s" % contest_name)

        safe_put_data(connection, "/users/", users, auth,
                      "sending users")

        safe_put_data(connection, "/tasks/", tasks, auth,
                      "sending tasks")

        return True

    @rpc_method
    def reinitialize(self):
        """Inform the service that something in the data of the
        contest has changed (users, tasks, the contest itself) and we
        need to do it over again. This should be almost like
        restarting the service.

        """
        logger.info("Reinitializing rankings.")
        self._initialize_scorers()
        for ranking in self.rankings:
            self.operation_queue.append((self.initialize, [ranking]))

    @rpc_method
    def new_evaluation(self, submission_id):
        """This RPC inform ScoringService that ES finished the
        evaluation for a submission.

        submission_id (int): the id of the submission that changed.

        """
        with SessionGen(commit=True) as session:
            submission = Submission.get_from_id(submission_id, session)
            if submission is None:
                logger.critical("[action_finished] Couldn't find "
                                " submission %d in the database" %
                                submission_id)
                return
            if submission.user.hidden:
                return

            # Assign score to the submission.
            scorer = self.scorers[submission.task_id]
            scorer.add_submission(submission_id, submission.timestamp,
                                  submission.user.username,
                                  [float(ev.outcome)
                                   for ev in submission.evaluations],
                                  submission.tokened())

            # Mark submission as scored.
            self.submission_ids_scored.add(submission_id)

            # Update the ranking view.
            contest = session.query(Contest).\
                      filter_by(id=self.contest_id).first()
            contest.update_ranking_view(self.scorers,
                                        task=submission.task)

            # Filling submission's score info in the db.
            submission.score = scorer.pool[submission_id]["score"]
            submission.public_score = \
                scorer.pool[submission_id]["public_score"]

            details = scorer.pool[submission_id]["details"]
            if details is None:
                details = []
            submission.score_details = json.dumps(details)

            public_details = scorer.pool[submission_id]["public_details"]
            if public_details is None:
                public_details = []
            submission.public_score_details = json.dumps(public_details)

            # Data to send to remote rankings.
            submission_url = "/submissions/%s" % encode_id(submission_id)
            submission_put_data = {
                "user": encode_id(submission.user.username),
                "task": encode_id(submission.task.name),
                "time": submission.timestamp}
            subchange_url = "/subchanges/%s" % encode_id("%s%ss" %
                                                         (submission.timestamp,
                                                          submission_id))
            subchange_put_data = {"submission": encode_id(submission_id),
                                  "time": submission.timestamp,
                                  "score": submission.score,
                                  "extra": details}

        # TODO: ScoreRelative here does not work with remote
        # rankings (it does in the ranking view) because we
        # update only the user owning the submission.

        # Adding operations to the queue.
        for ranking in self.rankings:
            self.operation_queue.append((send_submission,
                                         [ranking, submission_url,
                                          submission_put_data]))
            self.operation_queue.append((send_change,
                                         [ranking, subchange_url,
                                          subchange_put_data]))

    @rpc_method
    def submission_tokened(self, submission_id, timestamp):
        """This RPC inform ScoringService that the user has played the
        token on a submission.

        submission_id (int): the id of the submission that changed.
        timestamp (int): the time of the token.

        """
        with SessionGen(commit=False) as session:
            submission = Submission.get_from_id(submission_id, session)
            if submission is None:
                logger.error("Received request for "
                             "unexistent submission id %s." % submission_id)
                raise KeyError
            if submission.user.hidden:
                return

            # Mark submission as tokened.
            self.submission_ids_tokened.add(submission_id)

            # Data to send to remote rankings.
            submission_url = "/submissions/%s" % encode_id(submission_id)
            submission_put_data = {"user": encode_id(submission.user.username),
                            "task": encode_id(submission.task.name),
                            "time": submission.timestamp}
            subchange_url = "/subchanges/%s" % encode_id("%s%st" %
                                                         (timestamp,
                                                          submission_id))
            subchange_put_data = {"submission": encode_id(submission_id),
                                  "time": timestamp,
                                  "token": True}

        # Adding operations to the queue.
        for ranking in self.rankings:
            self.operation_queue.append((send_submission,
                                         [ranking, submission_url,
                                          submission_put_data]))
            self.operation_queue.append((send_change,
                                         [ranking, subchange_url,
                                          subchange_put_data]))

    @rpc_method
    def invalidate_submission(self,
                              submission_id=None,
                              user_id=None,
                              task_id=None):
        """Request for invalidating the scores of some submissions.

        The scores to be cleared are the one regarding 1) a submission
        or 2) all submissions of a user or 3) all submissions of a
        task or 4) all submission (if all parameters are None).

        submission_id (int): id of the submission to invalidate, or
                             None.
        user_id (int): id of the user we want to invalidate, or None.
        task_id (int): id of the task we want to invalidate, or None.

        """
        logger.info("Invalidation request received.")

        submission_ids = get_submissions(
            self.contest_id,
            submission_id, user_id, task_id)

        logger.info("Submissions to invalidate: %s" % len(submission_ids))
        if len(submission_ids) == 0:
            return

        with SessionGen(commit=True) as session:
            for submission_id in submission_ids:
                submission = Submission.get_from_id(submission_id, session)
                submission.invalidate_score()

        old_s = len(self.submission_ids_to_score)
        old_t = len(self.submission_ids_to_token)
        self.submission_ids_to_score = submission_ids + \
                                       self.submission_ids_to_score
        if old_s + old_t == 0:
            self.add_timeout(self.score_old_submissions, None,
                             0.5, immediately=False)


def main():
    """Parse arguments and launch service.

    """
    default_argument_parser("Score computer and relayer for CMS.",
                            ScoringService,
                            ask_contest=ask_for_contest).run()


if __name__ == "__main__":
    main()
