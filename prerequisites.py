#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2013 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2014 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2013 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2014 Artem Iglikov <artem.iglikov@gmail.com>
# Copyright © 2015 William Di Luigi <williamdiluigi@gmail.com>
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

"""Build and installation routines needed to run CMS (user creation,
configuration, and so on).

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import sys
import os
import shutil
import re
import pwd
import grp

from glob import glob


# Root directories for the /usr and /var trees.
USR_ROOT = os.path.join("/", "usr", "local")
VAR_ROOT = os.path.join("/", "var", "local")


def copyfile(src, dest, owner, perm, group=None):
    """Copy the file src to dest, and assign owner and permissions.

    src (string): the complete path of the source file.
    dest (string): the complete path of the destination file (i.e.,
                   not the destination directory).
    owner (as given by pwd.getpwnam): the owner we want for dest.
    perm (integer): the permission for dest (example: 0660).
    group (as given by grp.getgrnam): the group we want for dest; if
                                      not specified, use owner's
                                      group.

    """
    shutil.copy(src, dest)
    owner_id = owner.pw_uid
    if group is not None:
        group_id = group.gr_gid
    else:
        group_id = owner.pw_gid
    os.chown(dest, owner_id, group_id)
    os.chmod(dest, perm)


def try_delete(path):
    """Try to delete a given path, failing gracefully.

    """

    if os.path.isdir(path):
        try:
            os.rmdir(path)
        except OSError:
            print("[Warning] Skipping because directory is not empty: ", path)
    else:
        try:
            os.remove(path)
        except OSError:
            print("[Warning] File not found: ", path)


def makedir(dir_path, owner=None, perm=None):
    """Create a directory with given owner and permission.

    dir_path (string): the new directory to create.
    owner (as given by pwd.getpwnam): the owner we want for dest.
    perm (integer): the permission for dest (example: 0660).

    """
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    if perm is not None:
        os.chmod(dir_path, perm)
    if owner is not None:
        os.chown(dir_path, owner.pw_uid, owner.pw_gid)


def copytree(src_path, dest_path, owner, perm_files, perm_dirs):
    """Copy the *content* of src_path in dest_path, assigning the
    given owner and permissions.

    src_path (string): the root of the subtree to copy.
    dest_path (string): the destination path.
    owner (as given by pwd.getpwnam): the owner we want for dest.
    perm_files (integer): the permission for copied not-directories.
    perm_dirs (integer): the permission for copied directories.

    """
    for path in glob(os.path.join(src_path, "*")):
        sub_dest = os.path.join(dest_path, os.path.basename(path))
        if os.path.isdir(path):
            makedir(sub_dest, owner, perm_dirs)
            copytree(path, sub_dest, owner, perm_files, perm_dirs)
        elif os.path.isfile(path):
            copyfile(path, sub_dest, owner, perm_files)
        else:
            print("Error: unexpected filetype for file %s. Not copied" % path)


def ask(message):
    """Ask the user and return True if and only if one of the following holds:
    - the users responds "Y" or "y"
    - the "-y" flag was set as a CLI argument

    """
    return "-y" in sys.argv or raw_input(message) in ["Y", "y"]


def check_root(yes):
    """Check if the current user is or isn't root, and exit with an error
    message if needed.

    """

    if yes and os.geteuid() != 0:
        print("[Error] You must be root to do this, try using 'sudo'")
        exit(1)

    if not yes and os.geteuid() == 0:
        print("[Error] You must *not* be root to do this, try avoiding 'sudo'")
        exit(1)


def compile_l10n():
    """This function compiles localization files.

    """

    check_root(False)
    print("===== Compiling localization files")
    for locale in glob(os.path.join("cms", "server", "po", "*.po")):
        country_code = re.search(r"/([^/]*)\.po", locale).groups()[0]
        print("  %s" % country_code)
        path = os.path.join("cms", "server", "mo", country_code,
                            "LC_MESSAGES")
        makedir(path)
        os.system("msgfmt %s -o %s" % (locale, os.path.join(path, "cms.mo")))


def install_l10n():
    """This function installs compiled localization files.

    """

    check_root(True)
    root = pwd.getpwnam("root")

    print("===== Copying localization files")

    # Check if compile_l10n has been called
    for locale in glob(os.path.join("cms", "server", "po", "*.po")):
        country_code = re.search(r"/([^/]*)\.po", locale).groups()[0]
        print("  %s" % country_code)
        path = os.path.join("cms", "server", "mo", country_code, "LC_MESSAGES")
        compiled_path = os.path.join(path, "cms.mo")
        if not os.path.exists(compiled_path):
            print("[Error] %s not found" % (compiled_path))
            print("[Error] You must run the compile_l10n command")
            exit(1)
        elif os.path.getmtime(locale) > os.path.getmtime(compiled_path):
            print("[Warning] %s is newer than %s" % (locale, compiled_path))
            print("[Warning] Are you sure you ran the compile_l10n command?")

    for locale in glob(os.path.join("cms", "server", "po", "*.po")):
        country_code = re.search(r"/([^/]*)\.po", locale).groups()[0]
        print("  %s" % country_code)
        path = os.path.join("cms", "server", "mo", country_code, "LC_MESSAGES")
        dest_path = os.path.join(USR_ROOT, "share", "locale",
                                 country_code, "LC_MESSAGES")
        makedir(dest_path, root, 0755)
        copyfile(os.path.join(path, "cms.mo"),
                 os.path.join(dest_path, "cms.mo"),
                 root, 0644)


def compile_isolate():
    """This function compiles the isolate sandbox.

    """

    check_root(False)
    print("===== Compiling isolate")
    os.chdir("isolate")
    os.system("make")
    os.chdir("..")


def install_isolate():
    """This function installs the isolate sandbox.

    """

    check_root(True)
    root = pwd.getpwnam("root")
    try:
        cmsuser = pwd.getpwnam("cmsuser")
        cmsuser_grp = grp.getgrnam("cmsuser")
    except:
        print("[Error] The cmsuser doesn't exist yet")
        print("[Error] You need to run the install command at least once")
        exit(1)

    print("===== Copying isolate to /usr/local/bin/")

    # Check if compile_isolate() has been called
    if not os.path.exists(os.path.join("isolate", "isolate")):
        print("[Error] You must run the compile_isolate command first")
        exit(1)

    makedir(os.path.join(USR_ROOT, "bin"), root, 0755)
    copyfile(os.path.join(".", "isolate", "isolate"),
             os.path.join(USR_ROOT, "bin", "isolate"),
             root, 04750, group=cmsuser_grp)


def install_all():
    """This function prepares all that's needed to run CMS:
    - creation of cmsuser user
    - installation of isolate
    - installation of localization files
    - installation of configuration files
    and so on.

    """

    check_root(True)

    print("===== Creating user and group cmsuser")
    os.system("useradd cmsuser -c 'CMS default user' -M -r -s /bin/false -U")
    cmsuser = pwd.getpwnam("cmsuser")
    root = pwd.getpwnam("root")
    cmsuser_grp = grp.getgrnam("cmsuser")

    # Run compile_l10n() and compile_isolate() as *not* root
    if os.system("sudo -u %s %s compile_l10n" % (os.getenv("SUDO_USER"), sys.argv[0])):
        exit(1)
    if os.system("sudo -u %s %s compile_isolate" % (os.getenv("SUDO_USER"), sys.argv[0])):
        exit(1)

    install_l10n()
    install_isolate()

    # We set permissions for each manually installed files, so we want
    # max liberty to change them.
    old_umask = os.umask(0000)

    print("===== Copying configuration to /usr/local/etc/")
    makedir(os.path.join(USR_ROOT, "etc"), root, 0755)
    for conf_file_name in ["cms.conf", "cms.ranking.conf"]:
        conf_file = os.path.join(USR_ROOT, "etc", conf_file_name)
        # Skip if destination is a symlink
        if os.path.islink(conf_file):
            continue
        # If the config exists, check if the user wants to overwrite it
        if os.path.exists(conf_file):
            if not ask("The %s file is already installed, type Y to overwrite it: "
                        % (conf_file_name)):
                continue
        if os.path.exists(os.path.join(".", "config", conf_file_name)):
            copyfile(os.path.join(".", "config", conf_file_name),
                     conf_file, cmsuser, 0660)
        else:
            conf_file_name = "%s.sample" % conf_file_name
            copyfile(os.path.join(".", "config", conf_file_name),
                     conf_file, cmsuser, 0660)

    print("===== Creating directories")
    dirs = [os.path.join(VAR_ROOT, "log"),
            os.path.join(VAR_ROOT, "cache"),
            os.path.join(VAR_ROOT, "lib"),
            os.path.join(VAR_ROOT, "run"),
            os.path.join(USR_ROOT, "include"),
            os.path.join(USR_ROOT, "share")]
    for _dir in dirs:
        # Skip if destination is a symlink
        if os.path.islink(os.path.join(_dir, "cms")):
            continue
        makedir(_dir, root, 0755)
        _dir = os.path.join(_dir, "cms")
        makedir(_dir, cmsuser, 0770)

    print("===== Copying Polygon testlib")
    path = os.path.join("cmscontrib", "polygon", "testlib.h")
    dest_path = os.path.join(USR_ROOT, "include", "cms", "testlib.h")
    copyfile(path, dest_path, root, 0644)

    os.umask(old_umask)
    print("===== Done")

    print("""
   ###########################################################################
   ###                                                                     ###
   ###    Remember that you must now add yourself to the cmsuser group:    ###
   ###                                                                     ###
   ###       $ sudo usermod -a -G cmsuser <your user>                      ###
   ###                                                                     ###
   ###    You must also logout to make the change effective.               ###
   ###                                                                     ###
   ###########################################################################
    """)


def uninstall_all():
    """This function deletes all that was installed by the install() function:
    - deletion of the cmsuser user
    - deletion of isolate
    - deletion of localization files
    - deletion of configuration files
    and so on.

    """

    print("===== Deleting isolate from /usr/local/bin/")
    try_delete(os.path.join(USR_ROOT, "bin", "isolate"))

    print("===== Deleting configuration to /usr/local/etc/")
    if ask("Type Y if you really want to remove configuration files: "):
        for conf_file_name in ["cms.conf", "cms.ranking.conf"]:
            try_delete(os.path.join(USR_ROOT, "etc", conf_file_name))

    print("===== Deleting localization files")
    for locale in glob(os.path.join("cms", "server", "po", "*.po")):
        country_code = re.search(r"/([^/]*)\.po", locale).groups()[0]
        print("  %s" % country_code)
        dest_path = os.path.join(USR_ROOT, "share", "locale",
                                 country_code, "LC_MESSAGES")
        try_delete(os.path.join(dest_path, "cms.mo"))

    print("===== Deleting empty directories")
    dirs = [os.path.join(VAR_ROOT, "log"),
            os.path.join(VAR_ROOT, "cache"),
            os.path.join(VAR_ROOT, "lib"),
            os.path.join(VAR_ROOT, "run"),
            os.path.join(USR_ROOT, "include"),
            os.path.join(USR_ROOT, "share")]
    for _dir in dirs:
        if os.listdir(_dir) == []:
            try_delete(_dir)

    print("===== Deleting Polygon testlib")
    try_delete(os.path.join(USR_ROOT, "include", "cms", "testlib.h"))

    print("===== Deleting user and group cmsuser")
    try:
        for user in grp.getgrnam("cmsuser").gr_mem:
            os.system("gpasswd -d %s cmsuser" % (user))
        os.system("userdel cmsuser")
    except KeyError:
        print("[Warning] Group cmsuser not found")

    print("===== Done")


USAGE = """%s <command>

Available commands:
- compile_l10n
- compile_isolate
- install_l10n  (requires root)
- install_isolate  (requires root)
- install  (requires root)
- uninstall  (requires root)
""" % (sys.argv[0])


if __name__ == "__main__":
    if "compile_l10n" in sys.argv:
        compile_l10n()
    elif "compile_isolate" in sys.argv:
        compile_isolate()
    elif "install_l10n" in sys.argv:
        install_l10n()
    elif "install_isolate" in sys.argv:
        install_isolate()
    elif "install" in sys.argv:
        install_all()
    elif "uninstall" in sys.argv:
        uninstall_all()
    else:
        print(USAGE)
