# yugabyte-db-thirdparty

This repository contains Python-based automation to build and package third-party dependencies that are needed to build YugabyteDB. We package these dependencies as GitHub releases so that they can be downloaded by YugabyteDB CI/CD systems without having to rebuild them every time. Here is an example of how to build yugabyte-db-thirdparty and then YugabyteDB with Clang 15.

```bash
cd ~/code
git clone https://github.com/yugabyte/yugabyte-db-thirdparty.git
cd yugabyte-db-thirdparty
./build_thirdparty.sh --toolchain=llvm15
```

To use your local changes to yugabyte-db-thirdparty in a YugabyteDB build:

```
cd ~/code
git clone https://github.com/yugabyte/yugabyte-db.git
cd yugabyte-db
export YB_THIRDPARTY_DIR=~/code/yugabyte-db-thirdparty
./yb_build.sh --clang15
```

The [ci.yml](https://github.com/yugabyte/yugabyte-db-thirdparty/blob/master/.github/workflows/ci.yml) GitHub Actions workflow file contains multiple operating system and compiler configurations that we build and test regularly. Take a look at the command lines used in that file to get an idea of various usable combinations of parameters to the `build_thirdparty.sh` script.

The third-party dependencies themselves are described, each in its own Python file, in the [build_definitions](https://github.com/yugabyte/yugabyte-db-thirdparty/tree/master/python/build_definitions) directory.

## Modifying build definition for a dependency

To modify some dependency (e.g. glog):
* Look at the corresponding python file in build_definitions, e.g. https://github.com/yugabyte/yugabyte-db-thirdparty/blob/master/python/build_definitions/glog.py, to see where it is pulling the dependency from. Usually it is a GitHub repo, either the open-source upstream repo or our own fork.
* In case of glog, it is https://github.com/yugabyte/glog. Fork that repo on GitHub, to e.g. https://github.com/yourgithubusername/glog. Clone your fork of the repo and make all the necessary changes in your local checkout.
* To test locally, pass `local_archive` pointing to your clone path (`local_archive` is only meant for testing and should not be submitted in your PR):
```python
        super(GLogDependency, self).__init__(
            name='glog',
            version='0.4.0-yb-1',
            url_pattern='https://github.com/yugabyte/glog/archive/v{0}.tar.gz',
            local_archive='/path/to/glog',
            build_group=BUILD_GROUP_INSTRUMENTED)
```
* When you are done with your changes to the dependency, e.g. glog, get them checked into our fork, i.e. yugabyte/glog on GitHub, and create the next "official" Yugabyte tag for that dependency, e.g. 0.4.0-yb-2 (we usually add a `-yb-N` suffix to the upstream version).
* Reference the updated tag from the version field in the dependency's python file as shown below. **Remember to remove `local_archive`.**
```python
        super(GLogDependency, self).__init__(
            name='glog',
            version='0.4.0-yb-2', # Note the updated tag
            url_pattern='https://github.com/yugabyte/glog/archive/v{0}.tar.gz',
            build_group=BUILD_GROUP_INSTRUMENTED)
```

* Rebuild thirdparty (`--add-checksum` so it would auto-add the checksum for your archive):

```
./build_thirdparty.sh --toolchain=llvm15 --add-checksum
```
* Create a PR in yugabyte-db-thirdparty with a descriptive commit message.

## Ensuring a clean build
By default, we don't use separate directories for different "build types" in yugabyte-db-thirdparty unlike we do in YugabyteDB. Therefore, when changing to a different compiler family, compiler version, compiler flags, etc., it would be safest to remove build output before rebuilding:

```
rm -rf build installed
```

If you only need to clean the built files and not the installed files (or are ok with overwriting the installed files), you can use the `clean_thirdparty.sh` script. With no arguments, `clean_thirdparty.sh` will clean all dependencies. To only clean certain dependencies, pass them as command line arguments. For example, to clean only Abseil and TCMalloc:
```
clean_thirdparty.sh abseil tcmalloc
```


## Per-build type directories
During development, `--per-build-dirs` introduces per-built type subdirectories under `build` and `installed` directories. Note that `--per-build-dirs` does not work properly with the yugabyte-db build. You must build without `--per-build-dirs` for that.

```
$ ls build
clang14-x86_64
gcc11-x86_64
```

## Building and publishing a tarball manually

Most types of our YugabyteDB third-party dependencies tarballs are automatically built by GitHub Actions jobs in this repo and uploaded as GitHub releases. However, there are a couple of build types that still need to be built and published manually.

### Installing the `hub` tool

Download the latest release package of the `hub` tool for the appropriate platform from https://github.com/github/hub/releases/ and install it so that it is accessible on PATH.

### GitHub token

Set the GITHUB_TOKEN environment variable before running the commands below.

### Apple macOS arm64 (M1)

```
export YB_TARGET_ARCH=arm64
export PATH=/opt/homebrew/bin:$PATH
export YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX=macos-arm64
rm -rf venv
./clean_thirdparty.sh --all
mkdir -p ~/logs
./build_and_release.sh 2>&1 | tee ~/logs/build_thirdparty_$( date +Y-%m-%dT%H_%M_%S ).log
```

### Linux aarch64

```
export YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX=almalinux8-aarch64-clang15
export YB_BUILD_THIRDPARTY_EXTRA_ARGS="--toolchain=llvm15 --expected-major-compiler-version=15"
rm -rf venv
./clean_thirdparty.sh --all
mkdir -p ~/logs
./build_and_release.sh 2>&1 | tee ~/logs/build_thirdparty_$( date +Y-%m-%dT%H_%M_%S ).log
```

### Amazon Linux 2 aarch64

```
export YB_THIRDPARTY_ARCHIVE_NAME_SUFFIX=amzn2-aarch64-clang15
export YB_BUILD_THIRDPARTY_EXTRA_ARGS="--toolchain=llvm15 --expected-major-compiler-version=15"
rm -rf venv
./clean_thirdparty.sh --all
mkdir -p ~/logs
./build_and_release.sh 2>&1 | tee ~/logs/build_thirdparty_$( date +Y-%m-%dT%H_%M_%S ).log
```

### Checking if the release has been created

Check if your new releases appeared here:

https://github.com/yugabyte/yugabyte-db-thirdparty/releases

Use the search box with terms such as "aarch64" or "arm64":

* https://github.com/yugabyte/yugabyte-db-thirdparty/releases?q=aarch64&expanded=true
* https://github.com/yugabyte/yugabyte-db-thirdparty/releases?q=arm64&expanded=true

### Setting up a new release version branch

We have multiple branches in the yugabyte-db-thirdparty repository for various long-lived YugabyteDB releases, such as 2.4, 2.6, 2.8, 2.14, 2.17.3, etc.
There is a certain amount of setup necessary before such a branch is operational.

- Create the branch off of the corresponding commit. Typically it is the yugabyte-db-thirdparty commit specified in the thirdparty_archives.yml file of the appropriate branch of https://github.com/yugabyte/yugabyte-db of the corresponding release of YugabyteDB.
- Create a branch.txt file in the yugabyte-db-thirdparty branch with the branch name / version number.
- Add processing of the branch.txt file to the `build_and_release.sh` script of your branch.  The purpose of these changes is to read the branch.txt file, and if it is present, include the `v<version>-` prefix in the tag of generated release archives. If this logic is already present, skip this step.
```
diff --git a/build_and_release.sh b/build_and_release.sh
index 255056e..b66168e 100755
--- a/build_and_release.sh
+++ b/build_and_release.sh
@@ -155,7 +155,16 @@ fi

 original_repo_dir=$PWD
 git_sha1=$( git rev-parse HEAD )
-tag=v$( date +%Y%m%d%H%M%S )-${git_sha1:0:10}
+branch_file_path="$YB_THIRDPARTY_DIR/branch.txt"
+branch_name=""
+if [[ -f ${branch_file_path} ]]; then
+  branch_name=$(<"${branch_file_path}")
+fi
+tag=v
+if [[ -n ${branch_name} ]]; then
+  tag+="${branch_name}-"
+fi
+tag+=$( date +%Y%m%d%H%M%S )-${git_sha1:0:10}
```
- Include `[skip ci]` in the commit message for your branch setup commit to prevent useless builds and yugabyte-db-thirdparty releases from happening.

For example, see the following commits for yugabyte-db-thirdparty branches created earlier:
- [`13e6a0104886e8e0c891e4936564814039a9ae67`](https://github.com/yugabyte/yugabyte-db-thirdparty/commit/13e6a0104886e8e0c891e4936564814039a9ae67) (2.4)
- [`fe0425532c1fccc0cb638e4e8d08fe202300aaaf`](https://github.com/yugabyte/yugabyte-db-thirdparty/commit/fe0425532c1fccc0cb638e4e8d08fe202300aaaf) (2.6)
- [`604821d7210dd248937f7d2eb575503ab7827340`](https://github.com/yugabyte/yugabyte-db-thirdparty/commit/604821d7210dd248937f7d2eb575503ab7827340) (2.8)
- [`66b10387c67b82073ab79444a6ac721ad11672ac`](https://github.com/yugabyte/yugabyte-db-thirdparty/commit/66b10387c67b82073ab79444a6ac721ad11672ac) (2.14)


