import os
import sys
import site
import pkg_resources
import platform

DEPENDENCIES_FOLDER = 'deps'

def pre_init_plugin():
    extra_libs_path = os.path.abspath(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), DEPENDENCIES_FOLDER)
    )
    # add to python path
    site.addsitedir(extra_libs_path)
    # pkg_resources doesn't listen to changes on sys.path.
    pkg_resources.working_set.add_entry(extra_libs_path)

pre_init_plugin()
