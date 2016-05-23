#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2016 William Di Luigi <williamdiluigi@gmail.com>
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

"""This script works kind of like cmsImportTask, but it assumes that the task
already exists. Specifically, it will just add a new dataset (without
activating it.

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

# We enable monkey patching to make many libraries gevent-friendly
# (for instance, urllib3, used by requests)
import gevent.monkey
gevent.monkey.patch_all()

import argparse
import logging
import os

from cms import utf8_decoder
from cms.db import SessionGen, Task
from cms.db.filecacher import FileCacher

from cmscontrib.loaders import choose_loader, build_epilog


logger = logging.getLogger(__name__)


class DatasetImporter(object):

    """This script creates a dataset

    """

    def __init__(self, path, description, loader_class):
        self.file_cacher = FileCacher()
        self.description = description
        self.loader = loader_class(os.path.abspath(path), self.file_cacher)

    def do_import(self):
        """Get the task from the TaskLoader, but store *just* its dataset."""

        # Get the task
        task = self.loader.get_task(get_statement=False)
        __import__("pdb").set_trace()
        if task is None:
            return

        # Keep the dataset (and the task name) and delete the task
        dataset = task.active_dataset
        task_name = task.name
        del task

        # Change the default description, there is a unique constraint on
        # (Task.id, Dataset.description)
        if self.description is None:
            import petname
            dataset.description = petname.Generate(2, " ").title()
        else:
            dataset.description = self.description

        # Store the dataset
        logger.info("Creating new dataset for task %s on the database.",
                    task_name)

        with SessionGen() as session:
            # Check whether the task already exists
            old_task = session.query(Task) \
                              .filter(Task.name == task_name) \
                              .first()
            if old_task is not None:
                # Set the dataset's task to the old task
                dataset.task = None  # apparently, we *need* this
                dataset.task = old_task

                # Store it
                session.add(dataset)
            else:
                logger.error("The specified task does not exist. "
                             "Aborting, no dataset imported.")

            session.commit()
            dataset_id = dataset.id

        logger.info("Import finished (dataset id: %s).", dataset_id)


def main():
    """Parse arguments and launch process."""

    parser = argparse.ArgumentParser(
        description="Import a new dataset for an existing task in CMS.",
        epilog=build_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-L", "--loader",
        action="store", type=utf8_decoder,
        default=None,
        help="use the specified loader (default: autodetect)"
    )
    parser.add_argument(
        "-D", "--description",
        action="store", type=utf8_decoder,
        default=None,
        help="dataset description (default: generate a random readable string)"
    )
    parser.add_argument(
        "target",
        action="store", type=utf8_decoder,
        help="target file/directory from where to import the dataset"
    )

    args = parser.parse_args()

    loader_class = choose_loader(
        args.loader,
        args.target,
        parser.error
    )

    DatasetImporter(
        path=args.target,
        description=args.description,
        loader_class=loader_class
    ).do_import()


if __name__ == "__main__":
    main()
