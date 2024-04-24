# Copyright (c) Yugabyte, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
# in compliance with the License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License
# is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
# or implied. See the License for the specific language governing permissions and limitations
# under the License.
#


ADD_CHECKSUM_ARG = '--add-checksum'
ADD_CHECKSUM_ALTERNATE_ARG = ADD_CHECKSUM_ARG + 's'

# Environment variable names used for the build system to communicate with the compiler wrapper
# script. The unusal indentation below (9 spaces) is needed to make it easier to see the shared part
# of the Python constant name and its value. The PEP8 code style checker seems to be OK with that.


COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_APPEND = \
         'YB_COMPILER_WRAPPER_LD_FLAGS_TO_APPEND'

COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_REMOVE = \
         'YB_COMPILER_WRAPPER_LD_FLAGS_TO_REMOVE'

COMPILER_WRAPPER_ENV_VAR_NAME_TRACK_INCLUDES_IN_SUBDIRS_OF = \
         'YB_COMPILER_WRAPPER_TRACK_INCLUDES_IN_SUBDIRS_OF'

COMPILER_WRAPPER_ENV_VAR_NAME_SAVE_USED_INCLUDE_TAGS_IN_DIR = \
         'YB_COMPILER_WRAPPER_SAVE_USED_INCLUDE_TAGS_IN_DIR'

# We create a file with this name in every build directory to point back to the source directory
# from which the build directory was created.
SRC_PATH_FILE_NAME = 'yb_dep_src_path.txt'

GIT_CLONE_DEPTH = 10
