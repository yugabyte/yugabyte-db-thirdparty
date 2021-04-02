import shlex
import subprocess


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
