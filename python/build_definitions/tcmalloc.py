#
# Copyright (c) YugaByte, Inc.
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

from yugabyte_db_thirdparty.build_definition_helpers import *  # noqa
import glob
import os


class TCMallocDependency(Dependency):
    abseil_dep: Dependency

    def __init__(self) -> None:
        super(TCMallocDependency, self).__init__(
            name='tcmalloc',
            version='31549f83a1f2ca328dee482dd9ed338a2db4e88b',
            url_pattern='https://github.com/google/tcmalloc/archive/{0}.tar.gz',
            build_group=BuildGroup.POTENTIALLY_INSTRUMENTED)
        self.copy_sources = True

    def set_abseil_dep(self, abseil_dep: Dependency) -> None:
        self.abseil_dep = abseil_dep

    def get_additional_cxx_flags(self, builder: 'BuilderInterface') -> List[str]:
        cxx_flags = []
        if (builder.compiler_choice.is_clang() and
                builder.compiler_choice.is_llvm_major_version_at_least(18)):
            cxx_flags.append('-Wno-error=thread-safety-reference-return')
        if builder.compiler_choice.is_gcc():
            # tcmalloc's copts include -Werror, and our -Wall enables -Wclass-memaccess in GCC.
            cxx_flags.append('-Wno-error=class-memaccess')
        return cxx_flags

    def build(self, builder: BuilderInterface) -> None:
        log_prefix = builder.log_prefix(self)

        # Build against the Abseil sources that libabsl comes from, which may be a --dev-repo.
        abseil_src_dir = builder.fs_layout.get_source_path(self.abseil_dep)
        if not os.path.isdir(abseil_src_dir):
            raise IOError(
                f"Abseil source directory {abseil_src_dir} not found. Build abseil first.")
        builder.build_with_bazel(
            dep=self,
            targets=['//tcmalloc', '//tcmalloc:malloc_extension'],
            override_modules={'abseil-cpp': abseil_src_dir})

        # Abseil objects are compiled here only as dependencies and are not included, because
        # YugabyteDB links libabsl separately.
        object_files = sorted(
            glob.glob(os.path.join('bazel-bin', 'tcmalloc', '**', '*.o'), recursive=True))
        if not object_files:
            raise ValueError("Found no tcmalloc object files")
        static_lib_path = os.path.join(builder.prefix_lib, 'libgoogletcmalloc.a')
        remove_path(static_lib_path)
        builder.log_output(log_prefix, ['ar', 'qc', static_lib_path] + object_files)
        builder.log_output(log_prefix, ['ranlib', static_lib_path])

        shared_lib_name = f'libgoogletcmalloc.{builder.shared_lib_suffix}'
        builder.log_output(
            log_prefix,
            [builder.compiler_choice.get_cxx_compiler()] +
            builder.compiler_flags + builder.cxx_flags +
            ['-shared', '-o', os.path.join(builder.prefix_lib, shared_lib_name),
             '-Wl,-soname,' + shared_lib_name,
             '-Wl,--whole-archive', static_lib_path, '-Wl,--no-whole-archive',
             '-L' + builder.prefix_lib, '-labsl', '-lpthread'] +
            builder.ld_flags)

        # Copy headers, keeping the folder structure. https://stackoverflow.com/a/9626253/1890288.
        builder.log_output(log_prefix, ["rsync", "-a", "--include=*.h", "-f", "hide,! */",
                                        "./tcmalloc", builder.prefix_include])
