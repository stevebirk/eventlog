import sys
import re
import os
import os.path
import logging
import subprocess

_LOG = logging.getLogger(__name__)

_WAIT_THRESHOLD = 0.1
_TIMEOUT = 60  # 60 second timeout
_RETRY_LIMIT = 5
_RETRY_WAIT_THRESHOLD = 1

_COMMAND = [
    'wget',
    '-nv',
    '-E', '-H', '-k', '-K', '-p',
    '--user-agent=',
    '-e', 'robots=off',
    '--tries', str(_RETRY_LIMIT),
    '--waitretry', str(_RETRY_WAIT_THRESHOLD),
    '--timeout', str(_TIMEOUT),
    '--wait', str(_WAIT_THRESHOLD)
]


def parse_localized_path(output):
    # 2013-11-27 23:38:03 URL:<original url> [44756] -> "<new path>" [1]
    m = re.search(".* -> \"(.*)\".*\n", output.decode('utf-8'))

    if m is not None:
        return m.group(1)
    else:
        return None


def archive_url(url, rootdir, subdir, dry=False):

    command = _COMMAND[:]

    archive_dir = os.path.join(rootdir, subdir)

    if dry:
        # when in dry mode, write files to /tmp and remove them after
        cwd = '/tmp'
        command += ['--delete-after']
    else:
        cwd = archive_dir

    command.append(url)  # quote the url -- just in case

    _LOG.info('archiving url: %s to: %s', url, archive_dir)

    # create filepath if it doesn't exist
    if (not dry) and (not os.path.exists(archive_dir)):
        try:
            os.makedirs(archive_dir)
        except Exception:
            _LOG.exception(
                'unable to create archive directory: %s', archive_dir
            )
            return None

    res = None

    try:
        _LOG.debug('using command: %s', ' '.join(command))

        p = subprocess.Popen(
            command,
            stdout=open('/dev/null', 'w'),
            stderr=subprocess.PIPE,
            cwd=cwd
        )
        output, error = p.communicate()

        retcode = p.returncode

        if 0 < retcode < 8:
            _LOG.error(
                'unable to archive url: %s, returncode: %d, stderr:\n%s',
                url,
                retcode,
                str(error, 'utf-8')
            )
        else:
            localized_path = parse_localized_path(error)

            if localized_path is None:
                _LOG.error(
                    'unable to parse local archive path:\n%s',
                    str(error, 'utf-8')
                )
            else:
                res = os.path.join(subdir, localized_path)

    except Exception:
        _LOG.exception('unable to archive url: %s', url)
        res = None

    return res
