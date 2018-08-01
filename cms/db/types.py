#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2013 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2014-2018 Luca Wehrstedt <luca.wehrstedt@gmail.com>
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

"""Custom types for SQLAlchemy.

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future.builtins.disabled import *  # noqa
from future.builtins import *  # noqa

import psycopg2.extras
import sqlalchemy
from sqlalchemy import DDL, event, TypeDecorator, Unicode
from sqlalchemy.dialects.postgresql import ARRAY

from . import metadata


# Have psycopg2 use the Python types in ipaddress to represent the INET
# and CIDR data types of PostgreSQL.
psycopg2.extras.register_ipaddress()


# Taken from:
# http://docs.sqlalchemy.org/en/rel_1_0/dialects/postgresql.html#using-json-jsonb-with-array
# Some specialized types (like CIDR) have a natural textual
# representation and PostgreSQL automatically converts them to and from
# it. However that conversion isn't automatic when these types are
# wrapped inside an ARRAY (e.g., TEXT[] can't be automatically cast to
# CIDR[]). This subclass of ARRAY performs such casting explicitly for
# each entry.
class CastingArray(ARRAY):
    def bind_expression(self, bindvalue):
        return sqlalchemy.cast(bindvalue, self)


class Codename(TypeDecorator):
    """Check that the column uses a limited alphabet.

    Namely: latin letters (upper and lowercase), arabic digits, the
    underscore and the dash. It must also be non-empty.

    """

    domain_name = "CODENAME"
    impl = Unicode

    @classmethod
    def compile(cls, dialect=None):
        return cls.domain_name

    @classmethod
    def get_create_command(cls):
        return DDL("CREATE DOMAIN %(domain)s VARCHAR "
                   "CHECK (VALUE ~ '^[A-Za-z0-9_-]+$')",
                   context={"domain": cls.domain_name})

    @classmethod
    def get_drop_command(cls):
        return DDL("DROP DOMAIN %(domain)s",
                   context={"domain": cls.domain_name})


event.listen(metadata, "before_create", Codename.get_create_command())
event.listen(metadata, "after_drop", Codename.get_drop_command())


class Filename(TypeDecorator):
    """Check that the column is a filename using a simple alphabet.

    Namely: latin letters (upper and lowercase), arabic digits, the
    underscore, the dash and the dot (for extensions). However, `.` and
    `..` are forbidden since they have a special meaning in UNIX. It
    must also be non-empty.

    """

    domain_name = "FILENAME"
    impl = Unicode

    @classmethod
    def compile(cls, dialect=None):
        return cls.domain_name

    @classmethod
    def get_create_command(cls):
        return DDL("CREATE DOMAIN %(domain)s VARCHAR "
                   "CHECK (VALUE ~ '^[A-Za-z0-9_.-]+$') "
                   "CHECK (VALUE != '.') "
                   "CHECK (VALUE != '..')",
                   context={"domain": cls.domain_name})

    @classmethod
    def get_drop_command(cls):
        return DDL("DROP DOMAIN %(domain)s",
                   context={"domain": cls.domain_name})


event.listen(metadata, "before_create", Filename.get_create_command())
event.listen(metadata, "after_drop", Filename.get_drop_command())


class FilenameSchema(TypeDecorator):
    """Check that the column is a filename schema using a simple alphabet."""

    domain_name = "FILENAME_SCHEMA"
    impl = Unicode

    @classmethod
    def compile(cls, dialect=None):
        return cls.domain_name

    @classmethod
    def get_create_command(cls):
        return DDL("CREATE DOMAIN %(domain)s VARCHAR "
                   "CHECK (VALUE ~ '^[A-Za-z0-9_.-]+(\.%%l)?$') "
                   "CHECK (VALUE != '.') "
                   "CHECK (VALUE != '..')",
                   context={"domain": cls.domain_name})

    @classmethod
    def get_drop_command(cls):
        return DDL("DROP DOMAIN %(domain)s",
                   context={"domain": cls.domain_name})


event.listen(metadata, "before_create", FilenameSchema.get_create_command())
event.listen(metadata, "after_drop", FilenameSchema.get_drop_command())


class FilenameSchemaArray(TypeDecorator):
    """Check that the column is an array of filename schemas (as above)."""

    domain_name = "FILENAME_SCHEMA_ARRAY"
    impl = CastingArray(Unicode)

    @classmethod
    def compile(cls, dialect=None):
        return cls.domain_name

    @classmethod
    def get_create_command(cls):
        # Postgres allows the condition "<sth> <op> ALL (<array>)" that
        # is true iff for all elements of array "<sth> <op> <element>".
        # This works for (in)equality but, as the order of the operands
        # is preserved, it doesn't work for regexp matching, where the
        # syntax is "<text> ~ <pattern>". Our regexp operates on a per
        # character basis so we can work around it by concatenating the
        # items of the array (using array_to_string) and match the
        # regexp on the result.
        return DDL("CREATE DOMAIN %(domain)s VARCHAR[] "
                   "CHECK (array_to_string(VALUE, '') ~ '^[A-Za-z0-9_.%%-]*$') "
                   "CHECK (array_to_string(VALUE, ',') "
                   "       ~ '^([A-Za-z0-9_.-]+(\.%%l)?(,|$))*$') "
                   "CHECK ('.' != ALL(VALUE)) "
                   "CHECK ('..' != ALL(VALUE))",
                   context={"domain": cls.domain_name})

    @classmethod
    def get_drop_command(cls):
        return DDL("DROP DOMAIN %(domain)s",
                   context={"domain": cls.domain_name})


event.listen(metadata, "before_create",
             FilenameSchemaArray.get_create_command())
event.listen(metadata, "after_drop", FilenameSchemaArray.get_drop_command())


class Digest(TypeDecorator):
    """Check that the column is a valid SHA1 hex digest."""

    domain_name = "DIGEST"
    impl = Unicode

    # The fake digest used to mark a file as deleted in the backend.
    TOMBSTONE = "x"

    @classmethod
    def compile(cls, dialect=None):
        return cls.domain_name

    @classmethod
    def get_create_command(cls):
        return DDL("CREATE DOMAIN %(domain)s VARCHAR "
                   "CHECK (VALUE ~ '^([0-9a-f]{40}|%(tombstone)s)$')",
                   context={"domain": cls.domain_name,
                            "tombstone": cls.TOMBSTONE})

    @classmethod
    def get_drop_command(cls):
        return DDL("DROP DOMAIN %(domain)s",
                   context={"domain": cls.domain_name})


event.listen(metadata, "before_create", Digest.get_create_command())
event.listen(metadata, "after_drop", Digest.get_drop_command())
