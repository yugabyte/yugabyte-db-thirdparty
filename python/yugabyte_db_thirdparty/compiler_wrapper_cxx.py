#!/usr/bin/env python3

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yugabyte_db_thirdparty import compiler_wrapper  # noqa


def main() -> None:
    compiler_wrapper.run_compiler_wrapper(is_cxx=True)


if __name__ == '__main__':
    main()
