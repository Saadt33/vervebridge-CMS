#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2016 Peyman Jabbarzade Ganje <peyman.jabarzade@gmail.com>
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

"""
This script adds multiple testcases from the filesystem to an existing dataset.

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import argparse
import logging
import sys
import re

from cms import utf8_decoder
from cms.db import SessionGen, Task, Contest
from cmscommon.importers import import_testcases_from_zipfile

logger = logging.getLogger(__name__)


def main():
    """Parse arguments and launch process.

    """
    parser = argparse.ArgumentParser(description="Add an admin to CMS.")
    parser.add_argument("task_name", action="store", type=utf8_decoder,
                        help="name of task which tests will be attached to")
    parser.add_argument("file", action="store", type=utf8_decoder,
                        help="a zip file which contains tests")
    parser.add_argument("inputtemplate", action="store", type=utf8_decoder,
                        help="format of input")
    parser.add_argument("outputtemplate", action="store", type=utf8_decoder,
                        help="format of output")
    parser.add_argument("-p", "--public", action="store_true",
                        help="if tests should be public")
    parser.add_argument("-o", "--overwrite", action="store_true",
                        help="if tests can overwrite existing tests")
    parser.add_argument("-c", "--contest_name", action="store",
                        help="name of contest which tests will be attached to")
    args = parser.parse_args()

    with SessionGen() as session:
        task = session.query(Task)\
            .filter(Task.name == args.task_name).first()
        if not task:
            logger.error("No task called %s found." % args.task_name)
            return
        dataset = task.active_dataset
        if args.contest_name is not None:
            contest = session.query(Contest)\
                .filter(Contest.name == args.contest_name).first()
            if task.contest != contest:
                logger.error("%s is not in %s" %
                             (args.task_name, args.contest_name))
                return False
        archive = args.file

        # Get input/output file names templates
        input_template = args.inputtemplate
        output_template = args.outputtemplate
        input_re = re.compile(re.escape(input_template).replace("\\*",
                              "(.*)") + "$")
        output_re = re.compile(re.escape(output_template).replace("\\*",
                               "(.*)") + "$")

        try:
            successful_subject, successful_message = \
                import_testcases_from_zipfile(
                    session, dataset, archive, input_re,
                    output_re, args.overwrite, args.public)
        except Exception as error:
            logger.error(str(error))
        logger.info(successful_subject)
        logger.info(successful_message)
    return True


if __name__ == "__main__":
    sys.exit(0 if main() is True else 1)
