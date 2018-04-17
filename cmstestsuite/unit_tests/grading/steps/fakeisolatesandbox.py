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

"""A fake sandbox for tests."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa

from collections import deque
from io import BytesIO

from cms.grading.Sandbox import IsolateSandbox


class FakeIsolateSandbox(IsolateSandbox):
    """Isolate, with some fakeness sprinkled on top.

    This fake redefines execute_without_std to skip running the command and
    just create a fake log file; it also allows to generate fake files to
    answer get_file or get_file_to_string.

    """
    def __init__(self, multithreaded, file_cacher, name=None, temp_dir=None):
        super(FakeIsolateSandbox, self).__init__(
            multithreaded, file_cacher, name, temp_dir)
        self._fake_files = {}

        self._fake_execute_data = deque()

    def fake_file(self, path, content):
        self._fake_files[path] = content

    def fake_execute_data(self, success, stdout, stderr,
                          time, wall_time, memory, exit_status, signal=None):
        """Set the fake data for the corresponding execution.

        Can be called multiple times, and this allows the system under test
        to call execute_without_std multiple times.

        success (bool): return value for execute_without_std.
        stdout (bytes): content of the sandbox stdout_file.
        stderr (bytes): content of the sandbox stderr_file.
        time (float): CPU time in seconds.
        memory (int): memory used in KiB.
        exit_status (str): isolate's two-letter exit status.
        signal (int|None): terminating signal if not None

        """
        data = {}
        data["success"] = success
        data["stdout"] = stdout
        data["stderr"] = stderr

        # Prepare run.log file...
        logs = []
        if time is not None:
            logs.append("time:%f" % time)
        if wall_time is not None:
            logs.append("time-wall:%f" % wall_time)
        if memory is not None:
            # isolate reports in KiB
            logs.append("max-rss:%d" % memory)
            logs.append("cg-mem:%d" % memory)
        if exit_status is not None and exit_status != "OK":
            logs.append("status:%s" % exit_status)
        if signal is not None:
            logs.append("exitsig:%s" % signal)
        data["log"] = "\n".join(logs).encode("utf-8")

        self._fake_execute_data.append(data)

    def get_file(self, path, maxlen=1024):
        if path in self._fake_files:
            return BytesIO(self._fake_files[path])
        raise FileNotFoundError(path)

    def get_file_to_string(self, path, maxlen=1024):
        if path in self._fake_files:
            return self._fake_files[path]
        raise FileNotFoundError(path)

    def execute_without_std(self, command, wait=False):
        # This is only able to simulate blocking calls.
        assert wait is True

        assert len(self._fake_execute_data) > 0

        # Required for the correct operation of the base class.
        self.log = None
        self.exec_num += 1

        data = self._fake_execute_data.popleft()
        self.fake_file("run.log.%d" % self.exec_num, data["log"])
        if data["stdout"] is not None:
            assert self.stdout_file is not None
            self.fake_file(self.stdout_file, data["stdout"])
        if data["stderr"] is not None:
            assert self.stderr_file is not None
            self.fake_file(self.stderr_file, data["stderr"])

        return data["success"]
