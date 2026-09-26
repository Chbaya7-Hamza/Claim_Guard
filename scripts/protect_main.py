"""Protect the main branch on GitHub so that changes arrive only through reviewed, passing pull requests.

    GITHUB_TOKEN=<token> python scripts/protect_main.py [--repo OWNER/NAME] [--branch main] [--dry-run]

The token is a fine-grained personal access token for this one repository with "Administration: read and write". Create it at
https://github.com/settings/personal-access-tokens/new and delete it afterwards. The token is read from the environment, sent
only to api.github.com, and never printed.

What it sets on the branch:
  - a pull request is required, with 1 approving review, and the owner (CODEOWNERS) must be the one who approves
  - a new push to the pull request dismisses the earlier approval
  - the CI checks below must pass, and the branch must be up to date with main before it merges
  - every review conversation must be resolved
  - no force pushes and no deletion of the branch, for anyone
  - administrators are NOT forced to follow the rules (enforce_admins is off), so the owner can still fix main in an emergency
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

REQUIRED_CHECKS = [
    'build (syntax and install)',
    'test (Python 3.10)',
    'test (Python 3.12)',
    'test (Python 3.14)',
    'rules-accuracy (15 rules vs the answer key)',
    'security (pen-test suite, static analysis, dependencies, secrets)',
]


def payload():
    return {
        'required_status_checks': {'strict': True, 'contexts': REQUIRED_CHECKS},
        'enforce_admins': False,
        'required_pull_request_reviews': {
            'required_approving_review_count': 1,
            'dismiss_stale_reviews': True,
            'require_code_owner_reviews': True,
            'require_last_push_approval': False,
        },
        'restrictions': None,
        'required_linear_history': False,
        'allow_force_pushes': False,
        'allow_deletions': False,
        'required_conversation_resolution': True,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--repo', default='PublisherX02/Claim_Guard')
    p.add_argument('--branch', default='main')
    p.add_argument('--dry-run', action='store_true', help='print the rules that would be set and exit')
    a = p.parse_args()
    body = json.dumps(payload(), indent=2)
    if a.dry_run:
        print(f'PUT /repos/{a.repo}/branches/{a.branch}/protection\n{body}')
        return 0
    token = os.environ.get('GITHUB_TOKEN', '').strip()
    if not token:
        p.error('set GITHUB_TOKEN (see the top of this file for how to create one)')
    url = f'https://api.github.com/repos/{a.repo}/branches/{a.branch}/protection'
    if not url.startswith('https://api.github.com/'):
        p.error('refusing to send the token anywhere but api.github.com')
    req = urllib.request.Request(url, data=body.encode(), method='PUT', headers={
        'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310 (fixed https URL checked above)
            out = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f'GitHub refused ({e.code}): {e.read().decode()[:400]}', file=sys.stderr)
        return 1
    reviews = out.get('required_pull_request_reviews', {})
    print(f'{a.repo}@{a.branch} is protected: {reviews.get("required_approving_review_count")} approval(s), '
          f'code-owner review {reviews.get("require_code_owner_reviews")}, '
          f'{len(out.get("required_status_checks", {}).get("contexts", []))} required checks, force pushes off.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
