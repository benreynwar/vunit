# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2015, 2016, Lars Asplund lars.anders.asplund@gmail.com

"""
Interface for the Synopsys VCS MX simulator
"""

from __future__ import print_function
import os
import shutil
from os.path import join, dirname, abspath, relpath
import subprocess
import sys
import logging
from vunit.ostools import write_file, file_exists
from vunit.simulator_interface import (SimulatorInterface,
                                       ListOfStringOption,
                                       run_command,
)
from vunit.exceptions import CompileError
from vunit.vcsmx_setup_file import SetupFile
LOGGER = logging.getLogger(__name__)

class VCSMXInterface(SimulatorInterface):
    """
    Interface for the Synopsys VCS MX simulator
    """

    name = "vcsmx"
    supports_gui_flag = True
    package_users_depend_on_bodies = False

    compile_options = [
        ListOfStringOption("vcsmx.vcsmx_vhdl_flags"),
        ListOfStringOption("vcsmx.vcsmx_verilog_flags"),
    ]

    sim_options = [
        ListOfStringOption("vcsmx.vcsmx_sim_flags"),
    ]

    @staticmethod
    def add_arguments(parser):
        """
        Add command line arguments
        """
        group = parser.add_argument_group("Synopsys VCS MX",
                                          description="Synopsys VCS MX-specific flags")
        group.add_argument("--vcsmxsetup",
                           default=None,
                           help="The synopsys_sim.setup file to use. If not given, VUnit maintains its own file.")

    @classmethod
    def from_args(cls, output_path, args):
        """
        Create new instance from command line arguments object
        """
        return cls(prefix=cls.find_prefix(),
                   output_path=output_path,
                   log_level=args.log_level,
                   gui=args.gui,
                   vcsmxsetup=args.vcsmxsetup)

    @classmethod
    def find_prefix_from_path(cls):
        """
        Find VCS MX simulator from PATH environment variable
        """
        return cls.find_toolchain(['vcs'])

    @staticmethod
    def supports_vhdl_2008_contexts():
        """
        Returns True when this simulator supports VHDL 2008 contexts
        """
        return False

    def __init__(self,  # pylint: disable=too-many-arguments
                 prefix, output_path, gui=False, log_level=None, vcsmxsetup=None):
        self._prefix = prefix
        self._libraries = []
        self._output_path = output_path
        self._vhdl_standard = None
        self._gui = gui
        self._log_level = log_level
        if vcsmxsetup is None:
            self._vcsmxsetup = abspath('synopsys_sim.setup') ## FIXME: env var SYNOPSYS_SIM_SETUP is also possible
        else:
            self._vcsmxsetup = abspath(vcsmxsetup)
        self._create_vcsmxsetup()
        try:
            _sim_setup = os.environ(SYNOPSYS_SIM_SETUP)
            LOGGER.debug("Environment variable SYNOPSYS_SIM_SETUP is '%s'" % _sim_setup)
        except NameError:
            LOGGER.debug("Environment variable SYNOPSYS_SIM_SETUP is not set")
        LOGGER.debug("VCS MX Setup file is '%s'" % self._vcsmxsetup)

    def _create_vcsmxsetup(self):
        """
        Create the synopsys_sim.setup file in the output directory if it does not exist
        """
        contents = """\
-- synopsys_sim.setup: Defines the locations of compiled libraries.
-- NOTE: the library definitions in this file are handled by VUnit, other lines are kept intact
-- WORK > DEFAULT
-- DEFAULT : {0}/libraries/work
-- TIMEBASE = NS
""".format(self._output_path)

        write_file(self._vcsmxsetup, contents)

    def setup_library_mapping(self, project):
        """
        Compile project using vhdl_standard
        """
        mapped_libraries = self._get_mapped_libraries()

        for library in project.get_libraries():
            self._libraries.append(library)
            self.create_library(library.name, library.directory, mapped_libraries)

    def compile_source_file_command(self, source_file):
        """
        Returns the command to compile a single source file
        """
        if source_file.file_type == 'vhdl':
            return self.compile_vhdl_file_command(source_file)
        elif source_file.file_type == 'verilog':
            return self.compile_verilog_file_command(source_file)

        raise CompileError

    @staticmethod
    def _vhdl_std_opt(vhdl_standard):
        """
        Convert standard to format of VCS MX command line flag
        """
        if vhdl_standard == "2002":
            return "-vhdl08" # FIXME: no switch for 2002 in VCS MX
        elif vhdl_standard == "2008":
            return "-vhdl08"
        elif vhdl_standard == "87":
            return "-vhdl87"
        elif vhdl_standard == "93":
            return "" # default
        else:
            assert False

    def compile_vhdl_file_command(self, source_file):
        """
        Returns command to compile a VHDL file
        """
        cmd = join(self._prefix, 'vhdlan')
        args = []
        args += ['%s' % self._vhdl_std_opt(source_file.get_vhdl_standard())]
        args += ['-work %s' % source_file.library.name]
        args += ['-l %s/vcsmx_compile_vhdl_file_%s.log' % (self._output_path, source_file.library.name)]
        if not self._log_level == "debug":
            args += ['-q']
            args += ['-nc']
        else:
            args += ['-verbose']
        args += source_file.compile_options.get('vcsmx_vhdl_flags', [])
        args += ['%s' % source_file.name]
        argsfile = "%s/vcsmx_compile_vhdl_file_%s.args" % (self._output_path, source_file.library.name)
        write_file(argsfile, "\n".join(args))
        return [cmd, '-f', argsfile]

    def compile_verilog_file_command(self, source_file):
        """
        Returns commands to compile a Verilog file
        """
        cmd = join(self._prefix, 'vlogan')
        args = []
        args += ['-compile']
        args += ['-debug_all']
        args += ['-sverilog'] # SystemVerilog
        args += ['+v2k'] # Verilog 2001
        args += ['-work %s' % source_file.library.name]
        args += source_file.compile_options.get('vcsmx_verilog_flags', [])
        args += ['-l %s/vcsmx_compile_verilog_file_%s.log' % (self._output_path, source_file.library.name)]
        if not self._log_level == "debug":
            args += ['-q']
            args += ['-nc']
        else:
            args += ['-V']
            args += ['-notice']
            args += ['+libverbose']
        for include_dir in source_file.include_dirs:
            args += ['+incdir+%s' % include_dir]
        for key, value in source_file.defines.items():
            args += ['+define+%s=%s' % (key, value.replace('"','\\"'))]
        args += ['%s' % source_file.name]
        argsfile = "%s/vcsmx_compile_verilog_file_%s.args" % (self._output_path, source_file.library.name)
        write_file(argsfile, "\n".join(args))
        return [cmd, '-f', argsfile]

    def create_library(self, library_name, library_path, mapped_libraries=None):
        """
        Create and map a library_name to library_path
        """
        mapped_libraries = mapped_libraries if mapped_libraries is not None else {}

        if not file_exists(abspath(library_path)):
            os.makedirs(abspath(library_path))
        if not file_exists(abspath(library_path+"/64/")):
            os.makedirs(abspath(library_path+"/64/"))

        if library_name in mapped_libraries and mapped_libraries[library_name] == library_path:
            return

        vcsmx = SetupFile.parse(self._vcsmxsetup)
        vcsmx[library_name] = library_path
        vcsmx.write(self._vcsmxsetup)

    def _get_mapped_libraries(self):
        """
        Get mapped libraries from synopsys_sim.setup file
        """
        vcsmx = SetupFile.parse(self._vcsmxsetup)
        return vcsmx

    def simulate(self,  # pylint: disable=too-many-arguments, too-many-locals
                 output_path, library_name, entity_name, architecture_name, config, elaborate_only=False):
        """
        Elaborates and Simulates with entity as top level using generics
        """

        launch_gui = self._gui is not False and not elaborate_only

        cmd = join(self._prefix, 'vcs')
        shutil.copy(self._vcsmxsetup, output_path)
        vcsmxargs = []
        vcsmxargs += ['%s' % join('%s.%s' % (library_name, entity_name))]
        if not launch_gui:
            vcsmxargs += ['-ucli']
        vcsmxargs += ['-licqueue']
        vcsmxargs += ['-debug_all']
        if not self._log_level == "debug":
            vcsmxargs += ['-q']
            vcsmxargs += ['-nc']
        else:
            vcsmxargs += ['-V']
            vcsmxargs += ['-notice']
        vcsmxargs += ['-l %s/vcsmx.log' % (output_path)]
        generics = self._generic_args(entity_name, config.generics)
        genericsfile = "%s/vcsmx.generics" % (output_path)
        write_file(genericsfile, "\n".join(generics))
        vcsmxargs += ['-lca', '-gfile %s' % genericsfile]
        if config.options.get('vcsmx_sim_flags'):
            vcsmxargs += config.options.get('vcsmx_sim_flags')
        vcsmxargsfile = '%s/vcsmx.args' % output_path
        write_file(vcsmxargsfile, "\n".join(vcsmxargs))
        if not run_command([cmd, '-file', vcsmxargsfile], cwd=output_path):
            return False

        cmd = join(output_path, 'simv')
        simvargs = []
        simvargs += ['-l %s/simv.log' % (output_path)]
        dofile = '%s/simv.do' % output_path
        docmds = []
        if launch_gui:
            simvargs += ['-gui']
            docmds += ['']
        else:
            simvargs += ['-ucli']
            simvargs += ['-do "%s"' % dofile]
            docmds += ['run']
            docmds += ['quit']
        write_file(dofile, "\n".join(docmds))
        simvargsfile = '%s/simv.args' % output_path
        write_file(simvargsfile, "\n".join(simvargs))
        if not elaborate_only:
            if not run_command([cmd, ' '.join(simvargs)], cwd=output_path):
#            if not run_command([cmd, '-file', simvargsfile], cwd=output_path):
                return False
        return True

    @staticmethod
    def _generic_args(entity_name, generics):
        """
        Create VCS MX arguments for generics and parameters
        """
        args = []
        for name, value in generics.items():
            if _value_needs_quoting(value):
                args += ['''assign "%s" /%s/%s\n''' % (value, entity_name, name)]
            else:
                args += ['''assign %s /%s/%s\n''' % (value, entity_name, name)]
        return args

def _value_needs_quoting(value):
    if sys.version_info.major == 2:
        if isinstance(value, str) or isinstance(value, bool) or isinstance(value, unicode):
            return True
        else:
            return False
    else:
        if isinstance(value, str) or isinstance(value, bool):
            return True
        else:
            return False
