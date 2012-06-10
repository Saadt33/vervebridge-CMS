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

from cms.grading import get_compilation_command
from cms.grading.ParameterTypes import ParameterTypeCollection, \
     ParameterTypeChoice, ParameterTypeString
from cms.grading.TaskType import TaskType, \
     create_sandbox, delete_sandbox


class Batch(TaskType):
    """Task type class for a unique standalone submission source, with
    comparator (or not).

    Parameters needs to be a list of three elements.

    The first element is 'grader' or 'alone': in the first
    case, the source file is to be compiled with a provided piece of
    software ('grader'); in the other by itself.

    The second element is a 2-tuple of the input file name and output file
    name. The input file may be '' to denote stdin, and similarly the
    output filename may be '' to denote stdout.

    The third element is 'diff' or 'comparator' and says whether the
    output is compared with a simple diff algorithm or using a
    comparator.

    Note: the first element is used only in the compilation step; the
    others only in the evaluation step.

    A comparator can read argv[1], argv[2], argv[3] (respectively,
    input, correct output and user output) and should write the
    outcome to stdout and the text to stderr.

    """
    ALLOW_PARTIAL_SUBMISSION = False

    _COMPILATION = ParameterTypeChoice(
        "Compilation",
        "compilation",
        "",
        {"alone": "Submissions are self-sufficient",
         "grader": "Submissions are compiled with a grader"})

    _USE_FILE = ParameterTypeCollection(
        "I/O (blank for stdin/stdout)",
        "io",
        "",
        [
            ParameterTypeString("Input file", "inputfile", ""),
            ParameterTypeString("Output file", "outputfile", ""),
        ])

    _EVALUATION = ParameterTypeChoice(
        "Output evaluation",
        "output_eval",
        "",
        {"diff": "Outputs compared with white diff",
         "comparator": "Outputs are compared by a comparator"})

    ACCEPTED_PARAMETERS = [_COMPILATION, _USE_FILE, _EVALUATION]

    def compile(self):
        """See TaskType.compile."""
        # Detect the submission's language. The checks about the
        # formal correctedness of the submission are done in CWS,
        # before accepting it.
        language = self.submission.language

        # TODO: here we are sure that submission.files are the same as
        # task.submission_format. The following check shouldn't be
        # here, but in the definition of the task, since this actually
        # checks that task's task type and submission format agree.
        if len(self.submission.files) != 1:
            return self.finish_compilation(
                True, False, "Invalid files in submission",
                to_log="Submission contains %d files, expecting 1" %
                len(self.submission.files))

        # First and only one compilation.
        sandbox = create_sandbox(self)
        files_to_get = {}
        format_filename = self.submission.files.keys()[0]
        source_filenames = [format_filename.replace("%l", language)]
        files_to_get[source_filenames[0]] = \
            self.submission.files[format_filename].digest
        # If a grader is specified, we add to the command line (and to
        # the files to get) the corresponding manager.
        if self.parameters[0] == "grader":
            source_filenames.append("grader.%s" % language)
            files_to_get[source_filenames[1]] = \
                self.submission.task.managers["grader.%s" % language].digest
        executable_filename = format_filename.replace(".%l", "")
        command = get_compilation_command(language,
                                          source_filenames,
                                          executable_filename)
        operation_success, compilation_success, text = self.compilation_step(
            sandbox,
            command,
            files_to_get,
            {executable_filename: "Executable %s for submission %s" %
             (executable_filename, self.submission.id)})
        delete_sandbox(sandbox)

        # We had only one compilation, hence we pipe directly its
        # result to the finalization.
        return self.finish_compilation(operation_success, compilation_success,
                                       text)

    def evaluate_testcase(self, test_number):
        """See TaskType.evaluate_testcase."""
        sandbox = create_sandbox(self)

        # First step: execute the contestant program. This is also the
        # final step if we have a grader, otherwise we need to run also
        # a white_diff or a comparator.
        executable_filename = self.submission.executables.keys()[0]
        command = ["./%s" % executable_filename]
        executables_to_get = {
            executable_filename:
            self.submission.executables[executable_filename].digest
            }
        input_filename, output_filename = self.parameters[1]
        stdin_redirect = None
        stdout_redirect = None
        if input_filename == "":
            input_filename = "input.txt"
            stdin_redirect = input_filename
        if output_filename == "":
            output_filename = "output.txt"
            stdout_redirect = output_filename
        files_to_get = {
            input_filename: self.submission.task.testcases[test_number].input
            }
        allow_path = [input_filename, output_filename]
        success, outcome, text, plus = self.evaluation_step(
            sandbox,
            command,
            executables_to_get,
            files_to_get,
            self.submission.task.time_limit,
            self.submission.task.memory_limit,
            allow_path,
            stdin_redirect=stdin_redirect,
            stdout_redirect=stdout_redirect,
            final=False)
        # If an error occur (our or contestant's), return immediately.
        if not success or outcome is not None:
            delete_sandbox(sandbox)
            return self.finish_evaluation_testcase(
                test_number, success, outcome, text, plus)

        # Second step: diffing (manual or with comparator).
        if self.parameters[2] == "diff":
            # We white_diff output.txt and res.txt.
            success, outcome, text = self.white_diff_step(
                sandbox,
                output_filename, "res.txt",
                {"res.txt":
                 self.submission.task.testcases[test_number].output})
        elif self.parameters[2] == "comparator":
            # Manager present: wonderful, it'll do all the job.
            manager_filename = self.submission.task.managers.keys()[0]
            success, outcome, text, _ = self.evaluation_step(
                sandbox,
                ["./%s" % manager_filename,
                 input_filename, "res.txt", output_filename],
                {manager_filename:
                 self.submission.task.managers[manager_filename].digest},
                {"res.txt":
                 self.submission.task.testcases[test_number].output},
                allow_path=[input_filename, "res.txt", output_filename],
                final=True)
        else:
            raise ValueError("Unrecognized third parameter `%s' in for Batch "
                             "tasktype." % self.parameters[2])

        # Whatever happened, we conclude.
        delete_sandbox(sandbox)
        return self.finish_evaluation_testcase(
            test_number, success, outcome, text, plus)
