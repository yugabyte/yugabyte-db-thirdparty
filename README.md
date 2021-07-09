# yugabyte-db-thirdparty

This repository contains Python-based automation to build and package third-party dependencies that are needed to build YugabyteDB. We package these dependencies as GitHub releases so that they can be downloaded by YugabyteDB CI/CD systems without having to rebuild them every time. Here is an example of how to build yugabyte-db-thirdparty and then YugabyteDB with GCC 9, although many GCC and Clang versionsare usable.

```bash
cd ~/code
git clone https://github.com/yugabyte/yugabyte-db-thirdparty.git
cd yugabyte-db-thirdparty
./build_thirdparty.sh --devtoolset=9

cd ~/code
git clone https://github.com/yugabyte/yugabyte-db.git
cd yugabyte-db
export YB_THIRDPARTY_DIR=~/code/yugabyte-db-thirdparty
./yb_build.sh --gcc9
```

The [ci.yml](https://github.com/yugabyte/yugabyte-db-thirdparty/blob/master/.github/workflows/ci.yml) GitHub Actions workflow file contains multiple operating system and compiler configurations that we build and test regularly. Take a look at the command lines used in that file to get an idea of various usable combinations of parameters to the `build_thirdparty.sh` script.

The third-party dependencies themselves are described, each in its own Python file, in the [build_definitions](https://github.com/yugabyte/yugabyte-db-thirdparty/tree/master/python/build_definitions) directory.
