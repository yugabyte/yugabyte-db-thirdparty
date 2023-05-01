import shlex
import subprocess
import re

from typing import Tuple, Optional

from yugabyte_db_thirdparty import util
from yugabyte_db_thirdparty.custom_logging import log


def get_path_component_re_str(var_name: str) -> str:
    return r'(?P<%s>[^/]+)' % var_name


GITHUB_URL_PREFIX_RE_STR = ''.join([
    r'https?://github[.]com/',
    get_path_component_re_str('org_name'),
    '/',
    get_path_component_re_str('repo_name'),
])

GITHUB_ARCHIVE_DOWNLOAD_RE = re.compile(''.join([
    GITHUB_URL_PREFIX_RE_STR,
    '/archive/',
    r'(?:refs/tags/)?',
    get_path_component_re_str('tag'),
    '[.](tar[.]gz|zip|tgz)$',
]))

GITHUB_RELEASE_DOWNLOAD_RE = re.compile(''.join([
    GITHUB_URL_PREFIX_RE_STR,
    '/',
    'releases',
    '/'
    'download',
    '/',
    get_path_component_re_str('tag'),
    '/',
    '.*$'
]))


def get_current_git_branch_name(repo_path: str) -> str:
    return subprocess.check_output(
        shlex.split('git rev-parse --abbrev-ref HEAD'),
        cwd=repo_path
    ).strip().decode('utf-8')


def get_git_sha1(repo_path: str) -> str:
    return subprocess.check_output(
        shlex.split('git rev-parse HEAD'),
        cwd=repo_path
    ).strip().decode('utf-8')


def parse_github_url(url: str) -> Optional[Tuple[str, str, str]]:
    for pattern in [GITHUB_ARCHIVE_DOWNLOAD_RE, GITHUB_RELEASE_DOWNLOAD_RE]:
        m = pattern.match(url)
        if m:
            return m.group('org_name'), m.group('repo_name'), m.group('tag')
    return None


def git_clone(git_url: str, ref: str, repo_path: str, depth: int) -> None:
    log("Cloning repo %s to %s" % (git_url, repo_path))
    util.log_and_run_cmd([
        'git',
        'clone',
        git_url,
        '--branch',
        ref,
        '--depth',
        str(depth),
        repo_path,
    ])
