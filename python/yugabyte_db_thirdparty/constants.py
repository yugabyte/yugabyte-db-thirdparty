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

COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_APPEND = 'YB_COMPILER_WRAPPER_LD_FLAGS_TO_APPEND'
COMPILER_WRAPPER_ENV_VAR_NAME_LD_FLAGS_TO_REMOVE = 'YB_COMPILER_WRAPPER_LD_FLAGS_TO_REMOVE'
