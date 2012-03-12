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

"""Load the configuration.

"""

import os
import sys
import simplejson as json
import time
import datetime
import codecs
import netifaces
from argparse import ArgumentParser

from cms.async import ServiceCoord, Address, config as async_config
from cms.async.AsyncLibrary import RemoteService


## Configuration ##

class Config:
    """This class will contain the configuration for CMS. This needs
    to be populated at the initilization stage. This is loaded by
    default with some sane data. See cms.conf.sample in the examples
    for information on the meaning of the fields.

    """
    def __init__(self):
        """Default values for configuration, plus decide if this
        instance is running from the system path or from the source
        directory.

        """
        self.async = async_config

        # Database.
        self.database = "postgresql+psycopg2://cmsuser@localhost/cms"
        self.database_debug = False
        self.twophase_commit = False

        # Worker.
        self.keep_sandbox = True

        # WebServers.
        self.secret_key = "8e045a51e4b102ea803c06f92841a1fb",
        self.tornado_debug = False

        # ContestWebServer.
        self.contest_listen_address = [""]
        self.contest_listen_port = [8888]
        self.cookie_duration = 1800
        self.submit_local_copy = True
        self.submit_local_copy_path = "%s/submissions/"
        self.ip_lock = True
        self.block_hidden_users = False
        self.is_proxy_used = False
        self.max_submission_length = 100000
        self.min_submission_interval = 60
        self.stl_path = "/usr/share/doc/stl-manual/html/"

        # AdminWebServer.
        self.admin_listen_address = ""
        self.admin_listen_port = 8889

        # ScoringService.
        self.rankings_address = [["localhost", 8890]]
        self.rankings_username = ["usern4me"]
        self.rankings_password = ["passw0rd"]

        # ResourceService.
        self.process_cmdline = ["/usr/bin/python", "./%s.py", "%d"]

        # LogService.
        self.color_shell_log = True
        self.color_file_log = False
        self.color_remote_shell_log = True
        self.color_remote_file_log = True

        # Installed or from source?
        self.installed = sys.argv[0].startswith("/usr/") and \
            sys.argv[0] != '/usr/bin/ipython' and \
            sys.argv[0] != '/usr/bin/python'

        if self.installed:
            self.log_dir = os.path.join("/", "var", "local", "log", "cms")
            self.cache_dir = os.path.join("/", "var", "local", "cache", "cms")
            self.data_dir = os.path.join("/", "var", "local", "lib", "cms")
            paths = [os.path.join("/", "usr", "local", "etc", "cms.conf"),
                     os.path.join("/", "etc", "cms.conf")]
        else:
            self.log_dir = "log"
            self.cache_dir = "cache"
            self.data_dir = "lib"
            paths = [os.path.join(".", "examples", "cms.conf"),
                     os.path.join("/", "usr", "local", "etc", "cms.conf"),
                     os.path.join("/", "etc", "cms.conf")]

        # Allow user to override config file path using environment
        # variable 'CMS_CONFIG'.
        CMS_CONFIG_ENV_VAR = "CMS_CONFIG"
        if CMS_CONFIG_ENV_VAR in os.environ:
            paths = [os.environ[CMS_CONFIG_ENV_VAR]] + paths

        # Attempt to load a config file.
        self._load(paths)

    def _load(self, paths):
        """Try to load the config files one at a time, until one loads
        correctly.

        """
        for conf_file in paths:
            try:
                self._load_unique(conf_file)
            except IOError:
                pass
            except json.decoder.JSONDecodeError as error:
                print "Unable to load JSON configuration file %s " \
                      "because of a JSON decoding error.\n%r" % (conf_file,
                                                                 error)
            else:
                print "Using configuration file %s." % conf_file
                return
        else:
            print "Warning: no configuration file found " \
                  "in following locations:"
            for path in paths:
                print "    %s" % path
            print "Using default values."

    def _load_unique(self, path):
        """Populate the Config class with everything that sits inside
        the JSON file path (usually something like /etc/cms.conf). The
        only pieces of data treated differently are the elements of
        core_services and other_services that are sent to async
        config.

        path (string): the path of the JSON config file.

        """
        # Load config file
        dic = json.load(open(path))

        # Put core and test services in async_config
        for service in dic["core_services"]:
            for shard_number, shard in \
                    enumerate(dic["core_services"][service]):
                coord = ServiceCoord(service, shard_number)
                self.async.core_services[coord] = Address(*shard)
        del dic["core_services"]

        for service in dic["other_services"]:
            for shard_number, shard in \
                    enumerate(dic["other_services"][service]):
                coord = ServiceCoord(service, shard_number)
                self.async.other_services[coord] = Address(*shard)
        del dic["other_services"]

        # Put everything else.
        for key in dic:
            setattr(self, key, dic[key])


config = Config()


## ANSI utilities. See for reference:
# http://pueblo.sourceforge.net/doc/manual/ansi_color_codes.html

ANSI_FG_COLORS = {'black':   30,
                  'red':     31,
                  'green':   32,
                  'yellow':  33,
                  'blue':    34,
                  'magenta': 35,
                  'cyan':    36,
                  'white':   37}

ANSI_BG_COLORS = {'black':   40,
                  'red':     41,
                  'green':   42,
                  'yellow':  43,
                  'blue':    44,
                  'magenta': 45,
                  'cyan':    46,
                  'white':   47}

ANSI_RESET_CMD = 0
ANSI_FG_DEFAULT_CMD = 39
ANSI_BG_DEFAULT_CMD = 49
ANSI_BOLD_ON_CMD = 1
ANSI_BOLD_OFF_CMD = 22
ANSI_ITALICS_ON_CMD = 3
ANSI_ITALICS_OFF_CMD = 23
ANSI_UNDERLINE_ON_CMD = 4
ANSI_UNDERLINE_OFF_CMD = 24
ANSI_STRIKETHROUGH_ON_CMD = 9
ANSI_STRIKETHROUGH_OFF_CMD = 29
ANSI_INVERT_CMD = 7


def ansi_command(*args):
    """Produce the escape string that corresponds to the given ANSI
    command.

    """
    return '\033[%sm' % (";".join((str(x) for x in args)))


def ansi_color_hash(string):
    """Enclose a string in a ANSI code giving it a color that
    depends on its content.

    string (string): the string to color
    return (string): string enclosed in an ANSI code

    """
    # Magic number: 30 is the lowest of ANSI_FG_COLORS
    return 30 + (sum((ord(x) for x in string)) % len(ANSI_FG_COLORS))


def ansi_color_string(string, col):
    """Enclose a string in a ANSI code giving it the specified color.

    string (string): the string to color
    col (int): the color ANSI code
    return (string): s enclosed in an ANSI code

    """
    return ansi_command(col, ANSI_BOLD_ON_CMD) + \
        string + ansi_command(ANSI_RESET_CMD)


## Logging utilities ##

SEV_CRITICAL, SEV_ERROR, SEV_WARNING, SEV_INFO, SEV_DEBUG = \
              "CRITICAL", \
              "ERROR   ", \
              "WARNING ", \
              "INFO    ", \
              "DEBUG   "

SEVERITY_COLORS = {SEV_CRITICAL: 'red',
                   SEV_ERROR:    'red',
                   SEV_WARNING:  'yellow',
                   SEV_INFO:     'green',
                   SEV_DEBUG:    'cyan'}


def format_log(msg, coord, operation, severity, timestamp, colors=False):
    """Format a log message in a common way (for local and remote
    logging).

    msg (string): the message to log.
    coord (ServiceCoord): coordinate of the originating service.
    operation (string): a high-level description of the long-term
                        operation that is going on in the service.
    severity (string): a constant defined in Logger.
    timestamp (float): seconds from epoch.
    colors (bool): whether to use ANSI color commands (for the logs
                   directed to a shell).

    returns (string): the formatted log.

    """
    _datetime = datetime.datetime.fromtimestamp(timestamp)
    if coord is None:
        coord = ""

    if colors:
        severity_color = ANSI_FG_COLORS[SEVERITY_COLORS[severity]]
        coord_color = ansi_color_hash(coord)
        if operation == "":
            format_string = "%s [%s] %%s" % \
                (ansi_color_string("%s - %s", severity_color),
                 ansi_color_string("%s", coord_color))
        else:
            operation_color = ansi_color_hash(operation)
            format_string = "%s [%s/%s] %%s" % \
                (ansi_color_string("%s - %s", severity_color),
                 ansi_color_string("%s", coord_color),
                 ansi_color_string("%s", operation_color))
    else:
        if operation == "":
            format_string = "%s - %s [%s] %s"
        else:
            format_string = "%s - %s [%s/%s] %s"

    if operation == "":
        return format_string % ('{0:%Y/%m/%d %H:%M:%S}'.format(_datetime),
                                severity, coord, msg)
    else:
        return format_string % ('{0:%Y/%m/%d %H:%M:%S}'.format(_datetime),
                                severity, coord, operation, msg)


class Logger(object):
    """Utility class to connect to the remote log service and to
    store/display locally and remotely log messages.

    """
    TO_STORE = [
        SEV_CRITICAL,
        SEV_ERROR,
        SEV_WARNING,
        SEV_INFO,
        SEV_DEBUG,
        ]
    TO_DISPLAY = [
        SEV_CRITICAL,
        SEV_ERROR,
        SEV_WARNING,
        SEV_INFO
        ]
    # FIXME - SEV_DEBUG cannot be added to TO_SEND, otherwise we enter
    # an infinite loop
    TO_SEND = [
        SEV_CRITICAL,
        SEV_ERROR,
        SEV_WARNING,
        SEV_INFO
        ]

    # We use a singleton approach here. The following is the only
    # instance around.
    _instance = None

    def __new__(cls, *args, **kwargs):
        """Creation method to ensure there is only one logger around.

        """
        if not cls._instance:
            cls._instance = super(Logger, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        self._log_service = RemoteService(None,
                                          ServiceCoord("LogService", 0))
        self.operation = ""
        self._my_coord = None

    def initialize(self, service):
        """To be set by the service we are currently running.

        service (ServiceCoord): the service that we are running

        """
        self._my_coord = service

        # Warn if the service, shard is not supposed to be there.
        if self._my_coord not in config.async.core_services and \
           self._my_coord not in config.async.other_services:
            raise ValueError("Service not present in configuration.")

        log_dir = os.path.join(config.log_dir,
                               "%s-%d" % (service.name, service.shard))
        mkdir(config.log_dir)
        mkdir(log_dir)
        log_filename = "%d.log" % int(time.time())
        self._log_file = codecs.open(
            os.path.join(log_dir, log_filename),
            "w", "utf-8")
        try:
            os.remove(os.path.join(log_dir, "last.log"))
        except OSError:
            pass
        os.symlink(log_filename,
                   os.path.join(log_dir, "last.log"))
        self.info("%s %d up and running!" % service)

    def log(self, msg, operation=None, severity=None, timestamp=None):
        """Record locally a log message and tries to send it to the
        log service.

        msg (string): the message to log
        operation (string): a high-level description of the long-term
                            operation that is going on in the service
        severity (string): a constant defined in Logger
        timestamp (float): seconds from epoch

        """
        if severity is None:
            severity = SEV_INFO
        if timestamp is None:
            timestamp = time.time()
        if operation is None:
            operation = self.operation
        coord = repr(self._my_coord)

        if severity in Logger.TO_DISPLAY:
            print format_log(msg, coord, operation, severity, timestamp,
                             colors=config.color_shell_log)
        if self._my_coord is not None:
            if severity in Logger.TO_STORE:
                print >> self._log_file, format_log(
                    msg, coord, operation,
                    severity, timestamp,
                    colors=config.color_file_log)
            if severity in Logger.TO_SEND:
                self._log_service.Log(
                    msg=msg, coord=coord, operation=operation,
                    severity=severity, timestamp=timestamp)

    def __getattr__(self, method):
        """Syntactic sugar to allow, e.g., logger.debug(...).

        """
        severities = {
            "debug": SEV_DEBUG,
            "info": SEV_INFO,
            "warning": SEV_WARNING,
            "error": SEV_ERROR,
            "critical": SEV_CRITICAL
            }
        if method in severities:
            def new_method(msg, operation=None, timestamp=None):
                """Syntactic sugar around log().

                """
                return self.log(msg, operation, severities[method], timestamp)
            return new_method


# Create a (unique) logger object.
logger = Logger()


## Other utilities. ##

def default_argument_parser(description, cls, ask_contest=None):
    """Default argument parser for services - in two versions: needing
    a contest_id, or not.

    description (string): description of the service.
    cls (class): service's class.
    ask_contest (function): None if the service does not require a
                            contest, otherwise a function that returns
                            a contest_id (after asking the admins?)

    return (object): an instance of a service.

    """
    parser = ArgumentParser(description=description)
    parser.add_argument("shard", type=int)

    # We need to allow using the switch "-c" also for services that do
    # not need the contest_id because RS needs to be able to restart
    # everything without knowing which is which.
    contest_id_help = "id of the contest to automatically load"
    if ask_contest is None:
        contest_id_help += " (ignored)"
    parser.add_argument("-c", "--contest-id", help=contest_id_help,
                        nargs="?", type=int)
    args = parser.parse_args()
    if ask_contest is not None:
        if args.contest_id is not None:
            return cls(args.shard, args.contest_id)
        else:
            return cls(args.shard, ask_contest())
    else:
        return cls(args.shard)


def mkdir(path):
    """Make a directory without complaining for errors.

    path (string): the path of the directory to create
    returns (bool): True if the dir is ok, False if it is not

    """
    try:
        os.mkdir(path)
        return True
    except OSError:
        if os.path.isdir(path):
            return True
    return False


def find_local_addresses():
    """Returns the list of IPv4 addresses configured on the local
    machine.

    returns (list): a list of strings, each representing a local
                    IPv4 address.

    """
    addrs = []
    # Based on http://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
    for iface_name in netifaces.interfaces():
        addrs += [i['addr'] for i in netifaces.ifaddresses(iface_name). \
                      setdefault(netifaces.AF_INET, [])]
    return addrs
