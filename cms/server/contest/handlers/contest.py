#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2014 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2016 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2017 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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

"""Contest handler classes for CWS.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *
from future.builtins import *
from six import iterkeys, iteritems

import ipaddress
import logging
import pickle

from datetime import timedelta

import tornado.web

from sqlalchemy.orm import contains_eager
from werkzeug.datastructures import LanguageAccept
from werkzeug.http import parse_accept_header

from cms import config
from cms.db import Contest, Participation, User
from cms.server import compute_actual_phase, file_handler_gen, \
    create_url_builder
from cms.locale import filter_language_codes, choose_language_code
from cmscommon.datetime import get_timezone, make_datetime, make_timestamp

from .base import BaseHandler


logger = logging.getLogger(__name__)


NOTIFICATION_ERROR = "error"
NOTIFICATION_WARNING = "warning"
NOTIFICATION_SUCCESS = "success"


def check_ip(address, networks):
    """Return if client IP belongs to one of the accepted networks.

    address (bytes): IP address to verify.
    networks ([ipaddress.IPv4Network|ipaddress.IPv6Network]): IP
        networks (addresses w/ subnets) to check against.

    return (bool): whether the address belongs to one of the networks.

    """
    try:
        address = ipaddress.ip_address(str(address))
    except ValueError:
        return False

    for network in networks:
        if address in network:
            return True

    return False


class ContestHandler(BaseHandler):
    """A handler that has a contest attached.

    Most of the RequestHandler classes in this application will be a
    child of this class.

    """
    def __init__(self, *args, **kwargs):
        super(ContestHandler, self).__init__(*args, **kwargs)
        self.contest_url = None

    def prepare(self):
        super(ContestHandler, self).prepare()
        self.choose_contest()

        if self.contest.allowed_localizations:
            lang_codes = filter_language_codes(
                list(iterkeys(self.available_translations)),
                self.contest.allowed_localizations)
            self.available_translations = dict(
                (k, v) for k, v in iteritems(self.available_translations)
                if k in lang_codes)

        self.setup_locale()

        if self.is_multi_contest():
            self.contest_url = \
                create_url_builder(self.url(self.contest.name))
        else:
            self.contest_url = self.url

        # Run render_params() now, not at the beginning of the request,
        # because we need contest_name
        self.render_params()

    def choose_contest(self):
        """Fill self.contest using contest passed as argument or path.

        If a contest was specified as argument to CWS, fill
        self.contest with that; otherwise extract it from the URL path.

        """
        if self.is_multi_contest():
            # Choose the contest found in the path argument
            # see: https://github.com/tornadoweb/tornado/issues/1673
            contest_name = self.path_args[0]

            # Select the correct contest or return an error
            try:
                self.contest = self.contest_list[contest_name]
            except KeyError:
                self.contest = Contest(
                    name=contest_name, description=contest_name)
                # render_params in this class assumes the contest is loaded,
                # so we cannot call it without a fully defined contest. Luckily
                # the one from the base class is enough to display a 404 page.
                super(ContestHandler, self).render_params()
                raise tornado.web.HTTPError(404)
        else:
            # Select the contest specified on the command line
            self.contest = Contest.get_from_id(
                self.service.contest_id, self.sql_session)

    def get_current_user(self):
        """Return the currently logged in participation.

        The name is get_current_user because tornado requires that
        name.

        The participation is obtained from one of the possible sources:
        - if IP autologin is enabled, the remote IP address is matched
          with the participation IP address; if a match is found, that
          participation is returned; in case of errors, None is returned;
        - if username/password authentication is enabled, and the cookie
          is valid, the corresponding participation is returned, and the
          cookie is refreshed.

        After finding the participation, IP login and hidden users
        restrictions are checked.

        In case of any error, or of a login by other sources, the
        cookie is deleted.

        return (Participation|None): the participation object for the
            user logged in for the running contest.

        """
        cookie_name = self.contest.name + "_login"

        participation = None

        if self.contest.ip_autologin:
            try:
                participation = self._get_current_user_from_ip()
                # If the login is IP-based, we delete previous cookies.
                if participation is not None:
                    self.clear_cookie(cookie_name)
            except RuntimeError:
                return None

        if participation is None \
                and self.contest.allow_password_authentication:
            participation = self._get_current_user_from_cookie()

        if participation is None:
            self.clear_cookie(cookie_name)
            return None

        # Check if user is using the right IP (or is on the right subnet),
        # and that is not hidden if hidden users are blocked.
        ip_login_restricted = \
            self.contest.ip_restriction and participation.ip is not None \
            and not check_ip(self.request.remote_ip, participation.ip)
        hidden_user_restricted = \
            participation.hidden and self.contest.block_hidden_participations
        if ip_login_restricted or hidden_user_restricted:
            self.clear_cookie(cookie_name)
            participation = None

        return participation

    def _get_current_user_from_ip(self):
        """Return the current participation based on the IP address.

        return (Participation|None): the only participation matching
            the remote IP address, or None if no participations could
            be matched.

        raise (RuntimeError): if there is more than one participation
            matching the remote IP address.

        """
        try:
            # We encode it as a network (i.e., we assign it a /32 or
            # /128 mask) since we're comparing it for equality with
            # other networks.
            remote_ip = ipaddress.ip_network(str(self.request.remote_ip))
        except ValueError:
            return None
        participations = self.sql_session.query(Participation)\
            .filter(Participation.contest == self.contest)\
            .filter(Participation.ip.any(remote_ip))

        # If hidden users are blocked we ignore them completely.
        if self.contest.block_hidden_participations:
            participations = participations\
                .filter(Participation.hidden.is_(False))

        participations = participations.all()

        if len(participations) == 1:
            return participations[0]

        # Having more than participation with the same IP,
        # is a mistake and should not happen. In such case,
        # we disallow login for that IP completely, in order to
        # make sure the problem is noticed.
        if len(participations) > 1:
            logger.error("%d participants have IP %s while"
                         "auto-login feature is enabled." % (
                             len(participations), remote_ip))
            raise RuntimeError("More than one participants with the same IP.")

    def _get_current_user_from_cookie(self):
        """Return the current participation based on the cookie.

        If a participation can be extracted, the cookie is refreshed.

        return (Participation|None): the participation extracted from
            the cookie, or None if not possible.

        """
        cookie_name = self.contest.name + "_login"

        if self.get_secure_cookie(cookie_name) is None:
            return None

        # Parse cookie.
        try:
            cookie = pickle.loads(self.get_secure_cookie(cookie_name))
            username = cookie[0]
            password = cookie[1]
            last_update = make_datetime(cookie[2])
        except:
            return None

        # Check if the cookie is expired.
        if self.timestamp - last_update > \
                timedelta(seconds=config.cookie_duration):
            return None

        # Load participation from DB and make sure it exists.
        participation = self.sql_session.query(Participation)\
            .join(Participation.user)\
            .options(contains_eager(Participation.user))\
            .filter(Participation.contest == self.contest)\
            .filter(User.username == username)\
            .first()
        if participation is None:
            return None

        # Check that the password is correct (if a contest-specific
        # password is defined, use that instead of the user password).
        if participation.password is None:
            correct_password = participation.user.password
        else:
            correct_password = participation.password
        if password != correct_password:
            return None

        if self.refresh_cookie:
            self.set_secure_cookie(cookie_name,
                                   pickle.dumps((username,
                                                 password,
                                                 make_timestamp())),
                                   expires_days=None)

        return participation

    def setup_locale(self):
        lang_codes = list(iterkeys(self.available_translations))

        browser_langs = parse_accept_header(
            self.request.headers.get("Accept-Language", ""),
            LanguageAccept).values()
        automatic_lang = choose_language_code(browser_langs, lang_codes)
        if automatic_lang is None:
            automatic_lang = lang_codes[0]
        self.automatic_translation = \
            self.available_translations[automatic_lang]

        cookie_lang = self.get_cookie("language", None)
        if cookie_lang is not None:
            self.cookie_translation = self.available_translations[cookie_lang]
            chosen_lang = \
                choose_language_code([cookie_lang, automatic_lang], lang_codes)
        else:
            chosen_lang = automatic_lang
        self.translation = self.available_translations[chosen_lang]

        self._ = self.translation.gettext
        self.n_ = self.translation.ngettext

        self.set_header("Content-Language", chosen_lang)

    @staticmethod
    def _get_token_status(obj):
        """Return the status of the tokens for the given object.

        obj (Contest or Task): an object that has the token_* attributes.
        return (int): one of 0 (disabled), 1 (enabled/finite) and 2
                      (enabled/infinite).

        """
        if obj.token_mode == "disabled":
            return 0
        elif obj.token_mode == "finite":
            return 1
        elif obj.token_mode == "infinite":
            return 2
        else:
            raise RuntimeError("Unknown token_mode value.")

    def render_params(self):
        super(ContestHandler, self).render_params()

        self.r_params["contest"] = self.contest

        self.r_params["contest_url"] = self.contest_url

        self.r_params["phase"] = self.contest.phase(self.timestamp)

        self.r_params["printing_enabled"] = (config.printer is not None)
        self.r_params["questions_enabled"] = self.contest.allow_questions
        self.r_params["testing_enabled"] = self.contest.allow_user_tests

        if self.current_user is not None:
            participation = self.current_user

            res = compute_actual_phase(
                self.timestamp, self.contest.start, self.contest.stop,
                self.contest.analysis_start if self.contest.analysis_enabled
                else None,
                self.contest.analysis_stop if self.contest.analysis_enabled
                else None,
                self.contest.per_user_time, participation.starting_time,
                participation.delay_time, participation.extra_time)

            self.r_params["actual_phase"], \
                self.r_params["current_phase_begin"], \
                self.r_params["current_phase_end"], \
                self.r_params["valid_phase_begin"], \
                self.r_params["valid_phase_end"] = res

            if self.r_params["actual_phase"] == 0:
                self.r_params["phase"] = 0

            # set the timezone used to format timestamps
            self.r_params["timezone"] = get_timezone(participation.user,
                                                     self.contest)

        # some information about token configuration
        self.r_params["tokens_contest"] = self._get_token_status(self.contest)

        t_tokens = sum(self._get_token_status(t) for t in self.contest.tasks)
        if t_tokens == 0:
            self.r_params["tokens_tasks"] = 0  # all disabled
        elif t_tokens == 2 * len(self.contest.tasks):
            self.r_params["tokens_tasks"] = 2  # all infinite
        else:
            self.r_params["tokens_tasks"] = 1  # all finite or mixed

        self.r_params["available_translations"] = self.available_translations

        self.r_params["cookie_translation"] = self.cookie_translation
        self.r_params["automatic_translation"] = self.automatic_translation

        self.r_params["translation"] = self.translation
        self.r_params["_"] = self._

    def get_login_url(self):
        """The login url depends on the contest name, so we can't just
        use the "login_url" application parameter.

        """
        return self.contest_url()


FileHandler = file_handler_gen(ContestHandler)
