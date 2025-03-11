# Copyright (c) YugabyteDB, Inc.
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

# We create a file with this name in every build directory to point back to the source directory
# from which the build directory was created.
SRC_PATH_FILE_NAME = 'yb_dep_src_path.txt'

GIT_CLONE_DEPTH = 10

CXX_STANDARD = 23
OSX_CXX_STANDARD = '2b'
