# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2016, Lars Asplund lars.anders.asplund@gmail.com

"""
Handles Synopsys VCS MX synopsys_sim.setup files
"""

import re
from vunit.ostools import read_file, write_file


class SetupFile(dict):
    """
    Handles Synopsys VCS MX synopsys_sim.setup files

    Manages libraru definitions (with <name> : <path>), other lines are kept intact
    """

    _re_libdefine = re.compile(r'\s*([a-zA-Z0-9_]+)\s*:\s*(.*?)(#|$)')

    @classmethod
    def parse(cls, file_name):
        """
        Parse file_name and create SetupFile instance
        """
        contents = read_file(file_name)

        other_lines = []
        libdefines = {}
        for line in contents.splitlines():
            match = cls._re_libdefine.match(line)

            if match is None:
                other_lines.append(line)
            else:
                libdefines[match.group(1)] = match.group(2)
        return cls(libdefines, other_lines)

    def __init__(self, libdefines=None, other_lines=None):
        libdefines = {} if libdefines is None else libdefines
        other_lines = [] if other_lines is None else other_lines
        dict.__init__(self, libdefines)
        self._other_lines = other_lines

    def write(self, file_name):
        """
        Write synopsys_sim.setup file to file named 'file_name'
        """
        contents = "\n".join(self._other_lines +
                             ['%s : %s' % item
                              for item in sorted(self.items())]) + "\n"
        write_file(file_name, contents)
