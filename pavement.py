# -*- coding: utf-8 -*-
# This script file was fully taken from the ee_plugin: https://github.com/gee-community/qgis-earthengine-plugin.

import os
import platform
import fnmatch
import zipfile
import shutil

from paver.easy import *


def get_extlibs():
    if platform.system() == "Windows":
        return 'extlibs_windows'
    # if platform.system() == "Darwin":
    #     return 'extlibs_macos'
    if platform.system() == "Linux":
        return 'extlibs_linux'


options(
    plugin=Bunch(
        name='eurostat_downloader',
        ext_libs=path(get_extlibs()),
        source_dir=path('.'),
        package_dir=path('.'),
        tests=['test', 'tests'],
        excludes=[
            '.vscode',
            'ui',
            '.mypy_cache',
            'scripts',
            '*.pyc',
            '.git',
            '.idea',
            '.gitignore',
            '*/__pycache__',
            'eurostat_downloader.zip',
            'extlibs'
        ]
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
        if not files: return []
        # to prevent descending into dirs, modify the list in place
        for i in range(len(files) - 1, -1, -1):
            f = files[i]
            if exclude(f):
                files.remove(f)
        return files

    for root, dirs, files in os.walk(src_dir):
        for f in filter_excludes(files):
            relpath = os.path.relpath(root, '.')
            zipFile.write(path(root) / f, path('eurostat_downloader') / path(relpath) / f)
        filter_excludes(dirs)