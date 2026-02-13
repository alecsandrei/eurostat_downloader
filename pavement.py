# -*- coding: utf-8 -*-
# This script file was fully taken from the ee_plugin: https://github.com/gee-community/qgis-earthengine-plugin.

import fnmatch
import os
import zipfile

from paver.easy import *


options(
    plugin=Bunch(
        name='eurostat_downloader',
        source_dir=path('.'),
        package_dir=path('.'),
        tests=['test', 'tests'],
        excludes=[
            '.vscode',
            '.ruff_cache',
            '*.ui',
            '.mypy_cache',
            'scripts',
            '*.pyc',
            '*.zip',
            '.git',
            '.idea',
            '.gitignore',
            '*/__pycache__',
            'eurostat_downloader*.zip',
            '*/eurostat_cache',
            '*.pkl',
            '*.sh',
        ],
    ),
)


@task
@cmdopts([('tests', 't', 'Package tests with plugin')])
def package(options):
    package_file = options.plugin.package_dir / ('%s.zip' % options.plugin.name)
    with zipfile.ZipFile(package_file, 'w', zipfile.ZIP_LZMA) as f:
        if not hasattr(options.package, 'tests'):
            options.plugin.excludes.extend(options.plugin.tests)
        make_zip(f, options)


def make_zip(zipFile, options):
    excludes = set(options.plugin.excludes)

    src_dir = options.plugin.source_dir
    exclude = lambda p: any([fnmatch.fnmatch(p, e) for e in excludes])

    def filter_excludes(files):
        if not files:
            return []
        # to prevent descending into dirs, modify the list in place
        for i in range(len(files) - 1, -1, -1):
            f = files[i]
            if exclude(f):
                files.remove(f)
        return files

    for root, dirs, files in os.walk(src_dir):
        for f in filter_excludes(files):
            relpath = os.path.relpath(root, '.')
            zipFile.write(
                path(root) / f, path('eurostat_downloader') / path(relpath) / f
            )
        filter_excludes(dirs)
