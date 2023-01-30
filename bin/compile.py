#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.compile-and-package-for-windows"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023013001"
__version__ = "1.4.2"


import sys
import os
from command_runner import command_runner

# Insert parent dir as path se we get to use npbackup as package
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from npbackup.__main__ import __version__ as npbackup_version
from bin.NPBackupInstaller import __version__ as installer_version
from npbackup.customization import (
    COMPANY_NAME,
    TRADEMARKS,
    PRODUCT_NAME,
    FILE_DESCRIPTION,
    COPYRIGHT,
    LICENSE_FILE,
)
from npbackup.core.restic_source_binary import get_restic_internal_binary
from npbackup.path_helper import BASEDIR

del sys.path[0]

def check_private_build():
    private = False
    try:
        import npbackup._private_secret_keys

        print("WARNING: Building with private secret key")
        private = True
    except ImportError:
        try:
            import npbackup.secret_keys

            print("Building with default secret key")
        except ImportError:
            print("Cannot find secret keys")
            sys.exit()

    dist_conf_file_path = get_private_conf_dist_file()
    if "_private" in dist_conf_file_path:
        print("WARNING: Building with a private conf.dist file")
        private = True

    return private


def get_private_conf_dist_file():
    private_dist_conf_file = "_private_npbackup.conf.dist"
    dist_conf_file = "npbackup.conf.dist"
    dist_conf_file_path = os.path.join(BASEDIR, os.pardir, "examples", private_dist_conf_file)
    if os.path.isfile(dist_conf_file_path):
        print("Building with private dist config file")
    else:
        print("Building with default dist config file")
        dist_conf_file_path = os.path.join(BASEDIR, os.pardir, "examples", dist_conf_file)

    return dist_conf_file_path


def have_nuitka_commercial():
    try:
        import nuitka.plugins.commercial
        print("Running with nuitka commercial")
        return True
    except ImportError:
        print("Running with nuitka open source")
        return False


def compile(arch="64"):
    if os.name == "nt":
        program_executable = "npbackup.exe"
        restic_executable = "restic.exe"
    else:
        program_executable = "npbackup"
        restic_executable = "restic"

    PACKAGE_DIR = 'npbackup'

    is_private = check_private_build()
    build_dir = "BUILDS"
    build_dir += "-PRIVATE" if is_private else ""
    OUTPUT_DIR = os.path.abspath(os.path.join(BASEDIR, os.pardir, build_dir))

    if not os.path.isdir(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    PYTHON_EXECUTABLE = sys.executable

    # npbackup compilation
    # Strip possible version suffixes '-dev'
    _npbackup_version = npbackup_version.split("-")[0]
    PRODUCT_VERSION = _npbackup_version + ".0"
    FILE_VERSION = _npbackup_version + ".0"

    file_description = "{} P{}-{}{}".format(
        FILE_DESCRIPTION, sys.version_info[1], arch, "priv" if is_private else ""
    )

    restic_source_file = get_restic_internal_binary(arch)
    if not restic_source_file:
        print("Cannot find restic source file.")
        return
    restic_dest_file = os.path.join(PACKAGE_DIR, restic_executable)

    output_arch_dir = os.path.join(
        OUTPUT_DIR,
        "win-p{}{}-{}".format(sys.version_info[0], sys.version_info[1], arch),
    )

    translations_dir = "translations"
    translations_dir_source = os.path.join(BASEDIR, translations_dir)
    translations_dir_dest = os.path.join(PACKAGE_DIR, translations_dir)

    license_dest_file = os.path.join(PACKAGE_DIR, os.path.basename(LICENSE_FILE))

    icon_file = os.path.join(PACKAGE_DIR, 'npbackup_icon.ico')

    # Installer specific files, no need for a npbackup package directory here

    program_executable_path = os.path.join(output_arch_dir, program_executable)

    dist_conf_file_source = get_private_conf_dist_file()
    dist_conf_file_dest = os.path.basename(dist_conf_file_source.replace('_private_', ''))

    excludes_dir = "excludes"
    excludes_dir_source = os.path.join(BASEDIR, os.pardir, excludes_dir)
    excludes_dir_dest = excludes_dir

    NUITKA_OPTIONS = '--enable-plugin=data-hiding' if have_nuitka_commercial() else ''

    EXE_OPTIONS = '--company-name="{}" --product-name="{}" --file-version="{}" --product-version="{}" --copyright="{}" --file-description="{}" --trademarks="{}"'.format(
        COMPANY_NAME,
        PRODUCT_NAME,
        FILE_VERSION,
        PRODUCT_VERSION,
        COPYRIGHT,
        file_description,
        TRADEMARKS,
    )

    CMD = '{} -m nuitka --python-flag=no_docstrings --python-flag=-O {} {} --onefile --plugin-enable=tk-inter --include-data-dir="{}"="{}" --include-data-file="{}"="{}" --include-data-file="{}"="{}" --windows-icon-from-ico="{}" --output-dir="{}" bin/npbackup'.format(
        PYTHON_EXECUTABLE,
        NUITKA_OPTIONS,
        EXE_OPTIONS,
        translations_dir_source,
        translations_dir_dest,
        LICENSE_FILE,
        license_dest_file,
        restic_source_file,
        restic_dest_file,
        icon_file,
        output_arch_dir,
    )

    print(CMD)
    errors = False
    exit_code, output = command_runner(CMD, timeout=0, live_output=True)
    if exit_code != 0:
        errors = True

    # installer compilation
    _installer_version = installer_version.split("-")[0]
    PRODUCT_VERSION = _installer_version + ".0"
    FILE_VERSION = _installer_version + ".0"
    EXE_OPTIONS = '--company-name="{}" --product-name="{}" --file-version="{}" --product-version="{}" --copyright="{}" --file-description="{}" --trademarks="{}"'.format(
        COMPANY_NAME,
        PRODUCT_NAME,
        FILE_VERSION,
        PRODUCT_VERSION,
        COPYRIGHT,
        file_description,
        TRADEMARKS,
    )
    CMD = '{} -m nuitka --python-flag=no_docstrings --python-flag=-O {} {} --onefile --plugin-enable=tk-inter --include-data-file="{}"="{}" --include-data-file="{}"="{}" --include-data-dir="{}"="{}" --windows-icon-from-ico="{}" --windows-uac-admin --output-dir="{}" bin/NPBackupInstaller.py'.format(
        PYTHON_EXECUTABLE,
        NUITKA_OPTIONS,        
        EXE_OPTIONS,
        program_executable_path,
        program_executable,
        dist_conf_file_source,
        dist_conf_file_dest,
        excludes_dir_source,
        excludes_dir_dest,
        icon_file,
        output_arch_dir,
    )

    print(CMD)
    exit_code, output = command_runner(CMD, timeout=0, live_output=True)
    if exit_code != 0:
        errors = True

    print("COMPILE ERRORS", errors)


if __name__ == "__main__":
    # I know, I could improve UX here
    compile(arch=sys.argv[1])
    check_private_build()
