# yugabyte-db-thirdparty

This repository contains Python-based automation to build and package third-party dependencies that are needed to build YugabyteDB. We package these dependencies as GitHub releases so that they can be downloaded by YugabyteDB CI/CD systems without having to rebuild them every time. Here is an example of how to build yugabyte-db-thirdparty and then YugabyteDB with Clang 12.

```bash
cd ~/code
git clone https://github.com/yugabyte/yugabyte-db-thirdparty.git
cd yugabyte-db-thirdparty
./build_thirdparty.sh --toolchain=llvm12
```

To use your local changes to yugabyte-db-thirdparty in a YugabyteDB build:

```
cd ~/code
git clone https://github.com/yugabyte/yugabyte-db.git
cd yugabyte-db
export YB_THIRDPARTY_DIR=~/code/yugabyte-db-thirdparty
./yb_build.sh --clang12
```

The [ci.yml](https://github.com/yugabyte/yugabyte-db-thirdparty/blob/master/.github/workflows/ci.yml) GitHub Actions workflow file contains multiple operating system and compiler configurations that we build and test regularly. Take a look at the command lines used in that file to get an idea of various usable combinations of parameters to the `build_thirdparty.sh` script.

The third-party dependencies themselves are described, each in its own Python file, in the [build_definitions](https://github.com/yugabyte/yugabyte-db-thirdparty/tree/master/python/build_definitions) directory.

## Modifying build definition for a dependency

To modify some dependency (e.g. glog):
* Look at the corresponding python file in build_definitions, e.g. https://github.com/yugabyte/yugabyte-db-thirdparty/blob/master/python/build_definitions/glog.py, to see where it is pulling the dependency from. Usually it is a GitHub repo, either the open-source upstream repo or our own fork.
* In case of glog, it is https://github.com/yugabyte/glog. Fork that repo on GitHub, to e.g. https://github.com/yourgithubusername/glog. Make all the necessary changes in your fork, push changes to a branch on your fork, and create a tag, e.g. `0.4.0-yb-yourusername-1`. Push the tag to your fork.
* Modify the dependency python file, i.e. glog.py in this case, to reference your own repo and tag:

```python
        super(GLogDependency, self).__init__(
            name='glog',
            version='0.4.0-yb-yourusername-1',
            url_pattern='https://github.com/yourgithubyusername/glog/archive/v{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
```

* Rebuild thirdparty (`--add-checksum` so it would auto-add the checksum for your archive):

```
./build_thirdparty.sh --add-checksum
```

* When you are done with your changes to the dependency, e.g. glog, get them checked into our fork, i.e. yugabyte/glog on GitHub, and create the next "official" Yugabyte tag for that dependency, e.g. 0.4.0-yb-2 (we usually add a `-yb-N` suffix to the upstream version). Then in your PR to yugabyte-db-thirdparty, reference that tag from the dependency's python file as shown above.

## Ensuring a clean build

We don't currently use separate directories for different "build types" in yugabyte-db-thirdparty unlike we do in YugabyteDB. Therefore, when changing to a different compiler type, compiler flags, etc., it would be safest to remove build output before rebuilding:

```
rm -rf build installed
```
