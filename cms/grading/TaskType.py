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

"""In this file there is the basic infrastructure from which we can
build a task type.

Basically, a task type is a class that receives a submission and knows
how to compile and evaluate it. A worker creates a task type to work
on a submission, and all low-level details on how to implement the
compilation and the evaluation are contained in the task type class.

"""

import os
import codecs
import traceback

from cms import config, logger
from cms.grading import JobException
from cms.grading.Sandbox import Sandbox


## Automatic white diff. ##

WHITES = " \t\n\r"


def white_diff_canonicalize(string):
    """Convert the input string to a canonical form for the white diff
    algorithm; that is, the strings a and b are mapped to the same
    string by white_diff_canonicalize() if and only if they have to be
    considered equivalent for the purposes of the white_diff
    algorithm.

    More specifically, this function strips all the leading and
    trailing whitespaces from s and collapse all the runs of
    consecutive whitespaces into just one copy of one specific
    whitespace.

    string (string): the string to canonicalize.
    return (string): the canonicalized string.

    """
    # Replace all the whitespaces with copies of " ", making the rest
    # of the algorithm simpler
    for char in WHITES[1:]:
        string = string.replace(char, WHITES[0])

    # Split the string according to " ", filter out empty tokens and
    # join again the string using just one copy of the first
    # whitespace; this way, runs of more than one whitespaces are
    # collapsed into just one copy.
    string = WHITES[0].join([x for x in string.split(WHITES[0])
                             if x != ''])
    return string


def white_diff(output, res):
    """Compare the two output files. Two files are equal if for every
    integer i, line i of first file is equal to line i of second
    file. Two lines are equal if they differ only by number or type of
    whitespaces.

    Note that trailing lines composed only of whitespaces don't change
    the 'equality' of the two files. Note also that by line we mean
    'sequence of characters ending with \n or EOF and beginning right
    after BOF or \n'. In particular, every line has *at most* one \n.

    output (file): the first file to compare.
    res (file): the second file to compare.
    return (bool): True if the two file are equal as explained above.

    """

    while True:
        lout = output.readline()
        lres = res.readline()

        # Both files finished: comparison succeded
        if lres == '' and lout == '':
            return True

        # Only one file finished: ok if the other contains only blanks
        elif lres == '' or lout == '':
            lout = lout.strip(WHITES)
            lres = lres.strip(WHITES)
            if lout != '' or lres != '':
                return False

        # Both file still have lines to go: ok if they agree except
        # for the number of whitespaces
        else:
            lout = white_diff_canonicalize(lout)
            lres = white_diff_canonicalize(lres)
            if lout != lres:
                return False


## Sandbox lifecycle. ##

def create_sandbox(task_type):
    """Create a sandbox, and return it.

    task_type (TaskType): a task type instance.

    return (Sandbox): a sandbox.

    raise: JobException

    """
    try:
        sandbox = Sandbox(task_type.file_cacher)
    except (OSError, IOError):
        err_msg = "Couldn't create sandbox."
        logger.error("%s\n%s" % (err_msg, traceback.format_exc()))
        raise JobException(err_msg)
    return sandbox


def delete_sandbox(sandbox):
    """Delete the sandbox, if the configuration allows it to be
    deleted.

    sandbox (Sandbox): the sandbox to delete.

    """
    if not config.keep_sandbox:
        try:
            sandbox.delete()
        except (IOError, OSError):
            logger.warning("Couldn't delete sandbox.\n%s",
                           traceback.format_exc())


## Other stuff. ##

def append_path(path_list, new_path):
    """Append new_path to the path_list, inserting a colon inbetween.

    path_list (string): colon-separated list of paths.
    new_path (string): a new path to append to path_list.

    return (string): the concatenation.

    """
    if path_list == "":
        return new_path
    else:
        return "%s:%s" % (path_list, new_path)


def filter_ansi_escape(string):
    """Filter out ANSI commands from the given string.

    string (string): string to process.

    return (string): string with ANSI commands stripped.

    """
    ansi_mode = False
    res = ''
    for char in string:
        if char == u'\033':
            ansi_mode = True
        if not ansi_mode:
            res += char
        if char == u'm':
            ansi_mode = False
    return res


def extract_outcome_and_text(stdout, stderr):
    """Extract the outcome and the text from the two outputs of a
    managet (stdout contains the outcome, and stderr the text).

    stdout (string): filename of the standard output of the manager.
    stderr (string): filename of the standard error of the manager.

    return (float, string): outcome and text.
    raise: valueError if cannot decode the data.

    """
    with codecs.open(stdout, "r", "utf-8") as stdout_file:
        with codecs.open(stderr, "r", "utf-8") as stderr_file:
            try:
                outcome = stdout_file.readline().strip()
            except UnicodeDecodeError as error:
                logger.error("Unable to interpret manager stdout "
                             "(outcome) as unicode. %r" % error)
                raise ValueError("Cannot decode the outcome.")
            try:
                text = filter_ansi_escape(stderr_file.readline())
            except UnicodeDecodeError as error:
                logger.error("Unable to interpret manager stderr "
                             "(text) as unicode. %r" % error)
                raise ValueError("Cannot decode the text.")

    try:
        outcome = float(outcome)
    except ValueError:
        logger.error("Wrong outcome `%s' from manager." % outcome)
        raise ValueError("Outcome is not a float.")

    return outcome, text


class TaskType:
    """Base class with common operation that (more or less) all task
    types must do sometimes.

    - finish_(compilation, evaluation_testcase, evaluation): these
      finalize the given operation, writing back to the submission the
      new information, and deleting the sandbox if needed;

    - *_sandbox_*: these are utility to create and delete the sandbox,
       and to ask it to do some operation. If the operation fails, the
       sandbox is deleted.

    - (compilation, evaluation)_step: these execute one compilation or
      evaluation command in the sandbox.

    - compile, evaluate_testcase, evaluate: these actually do the
      operations; must be overloaded.

    """
    # If ALLOW_PARTIAL_SUBMISSION is True, then we allow the user to
    # submit only some of the required files; moreover, we try to fill
    # the non-provided files with the one in the previous submission.
    ALLOW_PARTIAL_SUBMISSION = False

    # A list of all the accepted parameters for this task type.
    # Each item is an instance of TaskTypeParameter.
    ACCEPTED_PARAMETERS = []

    @classmethod
    def parse_handler(cls, handler, prefix):
        """Ensure that the parameters list template agrees with the
        parameters actually passed.

        handler (Class): the Tornado handler with the parameters.
        prefix (string): the prefix of the parameter names in the
                         handler.

        return (list): parameters list correctly formatted, or
                       ValueError if the parameters are not correct.

        """
        new_parameters = []
        for parameter in cls.ACCEPTED_PARAMETERS:
            try:
                new_value = parameter.parse_handler(handler, prefix)
                new_parameters.append(new_value)
            except ValueError as error:
                raise ValueError("Invalid parameter %s: %s."
                                 % (parameter.name, error.message))
        return new_parameters

    def __init__(self, submission, parameters, file_cacher):
        """
        submission (Submission): the submission to grade.
        parameters (dict): parameters coming from the task; their
                           meaning depends on the specific TaskType.
        file_cacher (FileCacher): a FileCacher object to retrieve
                                  files from FS.

        """
        self.submission = submission
        self.result = {}
        self.parameters = parameters
        self.file_cacher = file_cacher

        self.worker_shard = None
        self.sandbox_paths = ""

        # If ignore_job is True, we conclude as soon as possible.
        self.ignore_job = False

    def finish_compilation(self, success, compilation_success=False,
                           text="", to_log=None):
        """Finalize the operation of compilation and build the
        dictionary to return to ES.

        success (bool): if the operation was successful (i.e., if cms
                        did everything in the right way).
        compilation_success (bool): if success = True, this is whether
                                    the compilation was successful
                                    (i.e., if the submission managed
                                    to compile).
        text (string): if success is True, stdout and stderr of the
                       compiler, or a message explaining why it
                       compilation_success is False.
        to_log (string): inform us that an unexpected event has
                         happened.

        return (dict): result collected during the evaluation.

        """
        if to_log is not None:
            logger.warning(to_log)
        self.result["success"] = success

        if success:
            if compilation_success:
                self.result["compilation_outcome"] = "ok"
            else:
                self.result["compilation_outcome"] = "fail"

            try:
                self.result["compilation_text"] = text.decode("utf-8")
            except UnicodeDecodeError:
                self.result["compilation_text"] = \
                    "Cannot decode compilation text."
                logger.error("Unable to decode UTF-8 for string %s." % text)

            self.result["compilation_shard"] = self.worker_shard
            self.result["compilation_sandbox"] = self.sandbox_paths
            self.sandbox_paths = ""

        self.ignore_job = False
        return self.result

    def finish_evaluation_testcase(self, test_number, success,
                                   outcome=0, text="", plus=None,
                                   to_log=None):
        """Finalize the operation of evaluating the submission on a
        testcase. Fill the information in the submission.

        test_number (int): number of testcase.
        success (bool): if the operation was successful.
        outcome (float): the outcome obtained by the submission on the
                         testcase.
        text (string): the reason of failure of the submission (if
                       any).
        plus (dict): additional information extracted from the logs of
                     the 'main' evaluation step - in particular,
                     memory and time information.
        to_log (string): inform us that an unexpected event has
                         happened.

        return (bool): success.

        """
        if to_log is not None:
            logger.warning(to_log)
        if "evaluations" not in self.result:
            self.result["evaluations"] = {}
        obj = self.result["evaluations"]
        obj[test_number] = {"success": success}
        if success:
            obj[test_number]["text"] = text
            obj[test_number]["outcome"] = outcome
            obj[test_number]["evaluation_shard"] = self.worker_shard
            obj[test_number]["evaluation_sandbox"] = self.sandbox_paths
            self.sandbox_paths = ""
        if plus is not None:
            for info in ["memory_used",
                         "execution_time",
                         "execution_wall_clock_time"]:
                obj[test_number][info] = plus.get(info, None)
        return success

    def finish_evaluation(self, success, to_log=None):
        """Finalize the operation of evaluating. Currently there is
        nothing to do.

        success (bool): if the evaluation was successful.
        to_log (string): inform us that an unexpected event has
                         happened.

        return (dict): result collected during the evaluation.

        """
        if to_log is not None:
            logger.warning(to_log)

        self.result["success"] = success
        if "evaluations" not in self.result:
            self.result["evaluations"] = {}

        self.ignore_job = False
        return self.result

    def compilation_step(self, sandbox, command, files_to_get,
                         executables_to_store):
        """Execute a compilation command in the sandbox. Note that in
        some task types, there may be more than one compilation
        commands (in others there can be none, of course).

        Note: this needs a sandbox already created.

        sandbox (Sandbox): the sandbox we consider.
        command (string): the actual compilation line.
        files_to_get (dict): digests of file to get from FS, indexed
                             by the filenames they should be put in.
        executables_to_store (dict): same filename -> digest format,
                                     indicate which files must be sent
                                     to FS and added to the Executable
                                     table in the db after a
                                     *successful* compilation (i.e.,
                                     one where the files_to_get
                                     compiled correctly).

        return (bool, bool, string, dict): True if compilation was
                                           successful; True if files
                                           compiled correctly;
                                           explainatory string;
                                           additional data.

        """
        # Record the usage of the sandbox.
        self.sandbox_paths = append_path(self.sandbox_paths, sandbox.path)

        # Copy all necessary files.
        for filename, digest in files_to_get.iteritems():
            sandbox.create_file_from_storage(filename, digest)

        # Set sandbox parameters suitable for compilation.
        sandbox.chdir = sandbox.path
        sandbox.preserve_env = True
        sandbox.filter_syscalls = 1
        sandbox.allow_syscall = ["waitpid", "prlimit64"]
        sandbox.allow_fork = True
        sandbox.file_check = 2
        # FIXME - File access limits are not enforced on children
        # processes (like ld).
        sandbox.set_env['TMPDIR'] = sandbox.path
        sandbox.allow_path = ['/etc/', '/lib/', '/usr/',
                              '%s/' % (sandbox.path)]
        sandbox.allow_path += ["/proc/self/exe"]
        sandbox.timeout = 10
        sandbox.wallclock_timeout = 20
        sandbox.address_space = 256 * 1024
        sandbox.stdout_file = sandbox.relative_path("compiler_stdout.txt")
        sandbox.stderr_file = sandbox.relative_path("compiler_stderr.txt")

        # Actually run the compilation command.
        logger.info("Starting compilation step.")
        box_success = sandbox.execute_without_std(command, wait=True)
        if not box_success:
            logger.error("Compilation aborted because of "
                         "sandbox error in `%s'." % sandbox.path)
            return False, None, None, None

        # Detect the outcome of the compilation.
        exit_status = sandbox.get_exit_status()
        exit_code = sandbox.get_exit_code()
        stdout = sandbox.get_file_to_string("compiler_stdout.txt")
        if stdout.strip() == "":
            stdout = "(empty)\n"
        stderr = sandbox.get_file_to_string("compiler_stderr.txt")
        if stderr.strip() == "":
            stderr = "(empty)\n"
        compiler_output = "Compiler standard output:\n" \
                          "%s\n" \
                          "Compiler standard error:\n" \
                          "%s" % (stdout, stderr)

        # From now on, we test for the various possible outcomes and
        # act appropriately.

        # Execution finished successfully and the submission was
        # correctly compiled.
        success = False
        compilation_success = None
        text = None

        if exit_status == Sandbox.EXIT_OK and exit_code == 0:
            self.result["executables"] = []
            for filename, digest in executables_to_store.iteritems():
                digest = sandbox.get_file_to_storage(filename, digest)
                self.result["executables"].append((filename, digest))
            logger.info("Compilation successfully finished.")
            success = True
            compilation_success = True
            text = "OK %s\n%s" % (sandbox.get_stats(), compiler_output)

        # Error in compilation: returning the error to the user.
        elif exit_status == Sandbox.EXIT_OK and exit_code != 0:
            logger.info("Compilation failed.")
            success = True
            compilation_success = False
            text = "Failed %s\n%s" % (sandbox.get_stats(), compiler_output)

        # Timeout: returning the error to the user
        elif exit_status == Sandbox.EXIT_TIMEOUT:
            logger.info("Compilation timed out.")
            success = True
            compilation_success = False
            text = "Time out %s\n%s" % (sandbox.get_stats(), compiler_output)

        # Suicide with signal (probably memory limit): returning the
        # error to the user
        elif exit_status == Sandbox.EXIT_SIGNAL:
            signal = sandbox.get_killing_signal()
            logger.info("Compilation killed with signal %s." % (signal))
            success = True
            compilation_success = False
            text = "Killed with signal %d %s.\nThis could be triggered by " \
                   "violating memory limits\n%s" % \
                   (signal, sandbox.get_stats(), compiler_output)

        # Sandbox error: this isn't a user error, the administrator
        # needs to check the environment
        elif exit_status == Sandbox.EXIT_SANDBOX_ERROR:
            logger.error("Compilation aborted because of sandbox error.")

        # Forbidden syscall: this shouldn't happen, probably the
        # administrator should relax the syscall constraints
        elif exit_status == Sandbox.EXIT_SYSCALL:
            syscall = sandbox.get_killing_syscall()
            logger.error("Compilation aborted "
                         "because of forbidden syscall %s." % syscall)

        # Forbidden file access: this could be triggered by the user
        # including a forbidden file or too strict sandbox contraints;
        # the administrator should have a look at it
        elif exit_status == Sandbox.EXIT_FILE_ACCESS:
            logger.error("Compilation aborted "
                         "because of forbidden file access.")

        # Why the exit status hasn't been captured before?
        else:
            logger.error("Shouldn't arrive here, failing.")

        return success, compilation_success, text

    def evaluation_step(self, sandbox, command,
                        executables_to_get, files_to_get,
                        time_limit=0, memory_limit=0,
                        allow_path=None,
                        stdin_redirect=None, stdout_redirect=None,
                        final=False):
        """Execute an evaluation command in the sandbox. Note that in
        some task types, there may be more than one evaluation
        commands (per testcase) (in others there can be none, of
        course).

        sandbox (Sandbox): the sandbox we consider.
        command (string): the actual execution line.
        executables_to_get (dict): digests of executables file to get
                                   from FS, indexed by the filenames
                                   they should be put in.
        files_to_get (dict): digests of file to get from FS, indexed
                             by the filenames they should be put in.
        time_limit (float): time limit in seconds.
        memory_limit (int): memory limit in MB.
        allow_path (list): list of relative paths accessible in the
                           sandbox.
        final (bool): if True, return last stdout and stderr as
                      outcome and text, respectively.

        return (bool, float, string dict): True if the evaluation was
                                           succesfull, or False (in
                                           this case we may stop the
                                           evaluation process); then
                                           there is outcome (or None)
                                           and explainatory text (or
                                           None), and additional data.

        """
        success = self.evaluation_step_before_run(
            sandbox, command, executables_to_get, files_to_get,
            time_limit, memory_limit, allow_path,
            stdin_redirect, stdout_redirect, wait=True)
        if not success:
            return False, None, None, None
        else:
            return self.evaluation_step_after_run(sandbox, final)

    def evaluation_step_before_run(self, sandbox, command,
                                   executables_to_get, files_to_get,
                                   time_limit=0, memory_limit=0,
                                   allow_path=None,
                                   stdin_redirect=None, stdout_redirect=None,
                                   wait=False):
        """First part of an evaluation step, until the running.

        return: exit code already translated if wait is True, the
                process if wait is False.

        """
        # Record the usage of the sandbox.
        self.sandbox_paths = ":".join([self.sandbox_paths, sandbox.path])

        # Copy all necessary files.
        for filename, digest in executables_to_get.iteritems():
            sandbox.create_file_from_storage(filename, digest, executable=True)
        for filename, digest in files_to_get.iteritems():
            sandbox.create_file_from_storage(filename, digest)

        if allow_path is None:
            allow_path = []

        # Set sandbox parameters suitable for evaluation.
        sandbox.chdir = sandbox.path
        sandbox.filter_syscalls = 2
        sandbox.timeout = time_limit
        sandbox.wallclock_timeout = 2 * time_limit
        sandbox.address_space = memory_limit * 1024
        sandbox.file_check = 1
        sandbox.allow_path = allow_path
        sandbox.stdin_file = stdin_redirect
        sandbox.stdout_file = stdout_redirect
        stdout_filename = os.path.join(sandbox.path, "stdout.txt")
        stderr_filename = os.path.join(sandbox.path, "stderr.txt")
        if sandbox.stdout_file is None:
            sandbox.stdout_file = stdout_filename
        sandbox.stderr_file = stderr_filename
        # These syscalls and paths are used by executables generated
        # by fpc.
        sandbox.allow_path += ["/proc/self/exe"]
        sandbox.allow_syscall += ["getrlimit",
                                  "rt_sigaction",
                                  "ugetrlimit"]
        # This one seems to be used for a C++ executable.
        sandbox.allow_path += ["/proc/meminfo"]

        # Actually run the evaluation command.
        logger.info("Starting evaluation step.")

        return sandbox.execute_without_std(command, wait=wait)

    def evaluation_step_after_run(self, sandbox, final=False):
        """Second part of an evaluation step, after the running.

        """
        stdout_filename = os.path.join(sandbox.path, "stdout.txt")
        stderr_filename = os.path.join(sandbox.path, "stderr.txt")

        # Detect the outcome of the execution.
        exit_status = sandbox.get_exit_status()

        # And retrieve some interesting data.
        plus = {
            "execution_time": sandbox.get_execution_time(),
            "execution_wall_clock_time":
                sandbox.get_execution_wall_clock_time(),
            "memory_used": sandbox.get_memory_used(),
            }

        success = False
        outcome = None
        text = None

        # Timeout: returning the error to the user.
        if exit_status == Sandbox.EXIT_TIMEOUT:
            logger.info("Execution timed out.")
            success = True
            outcome = 0.0
            text = "Execution timed out."

        # Suicide with signal (memory limit, segfault, abort):
        # returning the error to the user.
        elif exit_status == Sandbox.EXIT_SIGNAL:
            signal = sandbox.get_killing_signal()
            logger.info("Execution killed with signal %d." % signal)
            success = True
            outcome = 0.0
            text = "Execution killed with signal %d. " \
                   "This could be triggered by " \
                   "violating memory limits" % signal

        # Sandbox error: this isn't a user error, the administrator
        # needs to check the environment.
        elif exit_status == Sandbox.EXIT_SANDBOX_ERROR:
            logger.error("Evaluation aborted because of sandbox error.")

        # Forbidden syscall: returning the error to the user. Note:
        # this can be triggered also while allocating too much memory
        # dynamically (offensive syscall is mprotect).
        elif exit_status == Sandbox.EXIT_SYSCALL:
            msg = "Execution killed because of forbidden syscall %s." % \
                  sandbox.get_killing_syscall()
            logger.info(msg)
            success = True
            outcome = 0.0
            text = msg

        # Forbidden file access: returning the error to the user,
        # without disclosing the offending file (can't we?).
        elif exit_status == Sandbox.EXIT_FILE_ACCESS:
            msg = "Execution killed because of forbidden file access."
            logger.info("%s `%s'." % (msg, sandbox.get_forbidden_file_error()))
            success = True
            outcome = 0.0
            text = msg

        # Last check before assuming that evaluation finished
        # successfully; we accept the evaluation even if the exit code
        # isn't 0.
        elif exit_status != Sandbox.EXIT_OK:
            logger.error("Shouldn't arrive here, failing.")

        # If this isn't the last step of the evaluation, return that
        # the operation was successful, but neither an outcome nor an
        # explainatory text.
        elif not final:
            success = True

        # Otherwise, extract outcome and text from the manager.
        else:
            try:
                outcome, text = extract_outcome_and_text(stdout_filename,
                                                         stderr_filename)
            except ValueError:
                pass
            else:
                success = True

        return success, outcome, text, plus

    def white_diff_step(self, sandbox, output_filename,
                        correct_output_filename, files_to_get):
        """This is like an evaluation_step with final = True (i.e.,
        returns an outcome and a text). The outcome is 1.0 if and only
        if the two output files corresponds up to white_diff, 0.0
        otherwise.

        sandbox (Sandbox): the sandbox we consider.
        output_filename (string): the filename of user's output in the
                                  sandbox.
        correct_output_filename (string): the same with admin output.
        files_to_get (dict): files to get from storage.
        return (bool, float, string): see evaluation_step.

        """
        # Record the usage of the sandbox.
        self.sandbox_paths = append_path(self.sandbox_paths, sandbox.path)

        for filename, digest in files_to_get.iteritems():
            sandbox.create_file_from_storage(filename, digest)
        if sandbox.file_exists(output_filename):
            out_file = sandbox.get_file(output_filename)
            res_file = sandbox.get_file("res.txt")
            if white_diff(out_file, res_file):
                outcome = 1.0
                text = "Output is correct"
            else:
                outcome = 0.0
                text = "Output isn't correct"
        else:
            outcome = 0.0
            text = "Evaluation didn't produce file %s" % (output_filename)
        return True, outcome, text

    def compile(self):
        """Tries to compile the specified submission.

        It returns True when *our infrastracture* is successful (i.e.,
        the actual compilation may success or fail), and False when
        the compilation fails because of environmental problems
        (trying again to compile the same submission in a sane
        environment should lead to returning True).

        return (bool): success of operation.

        """
        raise NotImplementedError("Please subclass this class.")

    def evaluate_testcase(self, test_number):
        """Perform the evaluation of a single testcase.

        test_number (int): the number of the testcase to test.

        return (bool): True if the evaluation was successful.

        """
        raise NotImplementedError("Please subclass this class.")

    def evaluate(self):
        """Tries to evaluate the specified submission.

        It returns True when *our infrastracture* is successful (i.e.,
        the actual program may score or not), and False when the
        evaluation fails because of environmental problems (trying
        again to compile the same submission in a sane environment
        should lead to returning True).

        A default implementation which should suit most task types is
        provided.

        return (bool): success of operation.

        """
        for test_number in xrange(len(self.submission.task.testcases)):
            success = self.evaluate_testcase(test_number)
            if not success or self.ignore_job:
                return self.finish_evaluation(False)
        return self.finish_evaluation(True)
