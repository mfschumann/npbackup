#! /usr/bin/env python
#  -*- coding: utf-8 -*-
#
# This file is part of npbackup

__intname__ = "npbackup.gui.main"
__author__ = "Orsiris de Jong"
__copyright__ = "Copyright (C) 2022-2023 NetInvent"
__license__ = "GPL-3.0-only"
__build__ = "2023012501"


from typing import List
import os
from logging import getLogger
import re
import dateutil
import queue
from time import sleep
import PySimpleGUI as sg
from ofunctions.threading import threaded
from ofunctions.misc import BytesConverter
from customization import OEM_STRING, OEM_LOGO, loader_animation, folder_icon, file_icon, LICENSE_TEXT, LICENSE_FILE
from gui.config import config_gui
from core.runner import runner
from core.i18n_helper import _t


logger = getLogger(__intname__)

def _about_gui(version_string):
    license_content = LICENSE_TEXT
    try:
        with open(LICENSE_FILE, 'r') as file_handle:
            license_content = file_handle.read()
    except OSError:
        logger.info("Could not read license file.")
    
    layout = [
        [sg.Text(version_string)],
        [sg.Text('License: GNU GPLv3')],
        [sg.Multiline(license_content, size=(65, 20))],
        [sg.Button(_t('generic.accept'), key='exit')]
    ]

    window = sg.Window(_t('generic.about'), layout, keep_on_top=True)
    while True:
        event, _ = window.read()
        if event in [sg.WIN_CLOSED, 'exit']:
            break
    window.close()


@threaded
def _get_gui_data(config):
    action = {
        'action': 'list'
    }
    snapshots = runner(action=action, config=config)
    action = {
        'action': 'has_recent_snapshots'
    }

    current_state = runner(action=action, config=config)

    snapshot_list = []
    if snapshots:
        snapshots.reverse()  # Let's show newer snapshots first
        for snapshot in snapshots:
            snapshot_date = dateutil.parser.parse(snapshot["time"]).strftime("%Y-%m-%d %H:%M:%S")
            snapshot_username = snapshot['username']
            snapshot_hostname = snapshot["hostname"]
            snapshot_id = snapshot["short_id"]
            snapshot_list.append(
                "{} {} {} {}@{} [ID {}]".format(_t('main_gui.backup_from'), snapshot_date, _t('main_gui.run_as'), snapshot_username, snapshot_hostname, snapshot_id)
            )

    return current_state, snapshot_list


def get_gui_data(config):
    try:
        if not config['repo']['repository'] and not config['repo']['password']:
            sg.Popup(_t('main_gui.repository_not_configured'))
            return None, None
    except KeyError:
        sg.Popup(_t('main_gui.repository_not_configured'))
        return None, None
    action = {'action': 'check-binary'}
    result = runner(action=action, config=config)
    if not result:
        sg.Popup(_t('config_gui.no_binary'))
        return None, None
    thread = _get_gui_data(config)
    while not thread.done() and not thread.cancelled():
        sg.PopupAnimated(loader_animation, message=_t("main_gui.loading_data_from_repo"), time_between_frames=50, background_color='darkgreen')
    sg.PopupAnimated(None)
    return thread.result()


def _gui_update_state(window, current_state, snapshot_list):
    if current_state:
        window["state-button"].Update(_t("generic.up_to_date"), button_color=("white", "springgreen4"))
    elif current_state is False:
        window["state-button"].Update(
            _t("generic.too_old"), button_color=("white", "darkred")
        )
    elif current_state is None:
        window["state-button"].Update(
            _t("generic.not_connected"), button_color=("white", "darkgrey")
        )
    window["snapshot-list"].Update(snapshot_list)


@threaded
def _make_treedata_from_json(ls_result: List[dict]):
    """
    Treelist data construction from json input that looks like

    [
        {"time": "2023-01-03T00:16:13.6256884+01:00", "parent": "40e16692030951e0224844ea160642a57786a765152eae10940293888ee1744a", "tree": "3f14a67b4d7cfe3974a2161a24beedfbf62ad289387207eda1bbb575533dbd33", "paths": ["C:\\GIT\\npbackup"], "hostname": "UNIMATRIX0", "username": "UNIMATRIX0\\Orsiris", "id": "a2103ca811e8b081565b162cca69ab5ac8974e43e690025236e759bf0d85afec", "short_id": "a2103ca8", "struct_type": "snapshot"}

        {"name": "Lib", "type": "dir", "path": "/C/GIT/npbackup/.venv/Lib", "uid": 0, "gid": 0, "mode": 2147484159, "permissions": "drwxrwxrwx", "mtime": "2022-12-28T19:58:51.85719+01:00", "atime": "2022-12-28T19:58:51.85719+01:00", "ctime": "2022-12-28T19:58:51.85719+01:00", "struct_type": "node"}
        {'name': 'xpTheme.tcl', 'type': 'file', 'path': '/C/GIT/npbackup/npbackup.dist/tk/ttk/xpTheme.tcl', 'uid': 0, 'gid': 0, 'size': 2103, 'mode': 438, 'permissions': '-rw-rw-rw-', 'mtime': '2022-09-05T14:18:52+02:00', 'atime': '2022-09-05T14:18:52+02:00', 'ctime': '2022-09-05T14:18:52+02:00', 'struct_type': 'node'}
        {'name': 'unsupported.tcl', 'type': 'file', 'path': '/C/GIT/npbackup/npbackup.dist/tk/unsupported.tcl', 'uid': 0, 'gid': 0, 'size': 10521, 'mode': 438, 'permissions': '-rw-rw-rw-', 'mtime': '2022-09-05T14:18:52+02:00', 'atime': '2022-09-05T14:18:52+02:00', 'ctime': '2022-09-05T14:18:52+02:00', 'struct_type': 'node'}
        {'name': 'xmfbox.tcl', 'type': 'file', 'path': '/C/GIT/npbackup/npbackup.dist/tk/xmfbox.tcl', 'uid': 0, 'gid': 0, 'size': 27064, 'mode': 438, 'permissions': '-rw-rw-rw-', 'mtime': '2022-09-05T14:18:52+02:00', 'atime': '2022-09-05T14:18:52+02:00', 'ctime': '2022-09-05T14:18:52+02:00', 'struct_type': 'node'}
    ] 
    """
    treedata = sg.TreeData()
    
    # First entry of list of list should be the snapshot description and can be discarded
    # Since we use an iter now, first result was discarded by ls_window function already
    # ls_result.pop(0)
    for entry in ls_result:
        # Make sure we drop the prefix '/' so sg.TreeData does not get an empty root
        entry['path'] = entry['path'].lstrip('/')
        # Since Windows ignores case, we need to make tree keys lower or upper case only so 'C' and 'c' means the same
        # We only need to modifiy the tree key, the name will still retain case
        if os.name == 'nt':
            entry['path'] = entry['path'].lower()

        parent = os.path.dirname(entry['path'])

        # Make sure we normalize mtime, and remove microseconds 
        mtime = dateutil.parser.parse(entry["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
        if entry['type'] == 'dir' and entry['path'] not in treedata.tree_dict:
            treedata.Insert(parent=parent, key=entry['path'], text=entry['name'], values=['', mtime], icon=folder_icon)
        elif entry['type'] == 'file':
            size = BytesConverter(entry['size']).human
            treedata.Insert(parent=parent, key=entry['path'], text=entry['name'], values=[size, mtime], icon=file_icon)
    return treedata


@threaded
def _ls_window(config, snapshot_id):
    action = {
        "action": "ls",
        "snapshot": snapshot_id,
    }
    result = runner(action=action, config=config)
    if not result:
        return result, None

    # Since ls returns an iter now, we need to use next
    snapshot_id = next(result)
    try:
        snap_date = dateutil.parser.parse(snapshot_id['time'])
    except (KeyError, IndexError):
        snap_date = '[inconnu]'
    try:
        short_id = snapshot_id['short_id']
    except (KeyError, IndexError):
        short_id = '[inconnu]'
    try:
        username = snapshot_id['username']
    except (KeyError, IndexError):
        username = '[inconnu]'
    try:
        hostname = snapshot_id['hostname']
    except (KeyError, IndexError):
        hostname = '[inconnu]'


    backup_content = " {} {} {} {}@{} {} {}".format(_t('main_gui.backup_content_from'), snap_date, _t('main_gui.run_as'), username, hostname, _t('main_gui.identified_by'), short_id)
    return backup_content, result


def ls_window(config, snapshot):
    snapshot_id = re.match(r".*\[ID (.*)\].*", snapshot).group(1)
    thread = _ls_window(config, snapshot_id)
    
    while not thread.done() and not thread.cancelled():
        sg.PopupAnimated(loader_animation, message="{}. {}".format(_t('main_gui.loading_data_from_repo'), _t('main_gui.this_will_take_a_while')), time_between_frames=150, background_color='darkgreen')
    sg.PopupAnimated(None)
    backup_content, ls_result = thread.result()
    if not backup_content:
        sg.PopupError(_t("main_gui.cannot_get_content"), keep_on_top=True)
        return False

    # Preload animation before thread so we don't have to deal with slow initial drawing due to cpu usage of thread
    # This is an arbitrary way to make sure we get to see the popup
    sg.PopupAnimated(loader_animation, message="{}...".format(_t('main_gui.creating_tree')), time_between_frames=1, background_color='darkgreen')
    sleep(.01)
    sg.PopupAnimated(loader_animation, message="{}...".format(_t('main_gui.creating_tree')), time_between_frames=1, background_color='darkgreen')
    thread = _make_treedata_from_json(ls_result)
    
    while not thread.done() and not thread.cancelled():
        sg.PopupAnimated(loader_animation, message="{}...".format(_t('main_gui.creating_tree')), time_between_frames=150, background_color='darkgreen')
    sg.PopupAnimated(None)
    treedata = thread.result()

    left_col = [
        [sg.Text(backup_content)],
        [sg.Tree(data=treedata,
                   headings=[_t('generic.size'), _t('generic.modification_date')],
                   auto_size_columns=True,
                   select_mode=sg.TABLE_SELECT_MODE_EXTENDED,
                   num_rows=40,
                   col0_heading=_t("generic.path"),
                   col0_width=80,
                   key='-TREE-',
                   show_expanded=False,
                   enable_events=True,
                   expand_x=True,
                   expand_y=True,
                   vertical_scroll_only=False,
                   ),],
        [sg.Button(_t("main_gui.restore_to"), key='restore_to'), sg.Button(_t("generic.quit"), key="quit")]
    ]
    layout = [[sg.Column(left_col, element_justification="C")]]
    window = sg.Window(_t("generic.content"), layout=layout, grab_anywhere=True, keep_on_top=False)
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_CLOSE_ATTEMPTED_EVENT, "quit"):
            break
        if event == "restore_to":
            if not values['-TREE-']:
                sg.PopupError(_t('main_gui.select_folder'))
                continue
            restore_window(config, snapshot_id, values["-TREE-"])
    window.close()


@threaded
def _restore_window(action, config):
    return runner(action=action, config=config)


def restore_window(config, snapshot_id, includes):
    left_col = [
        [
            sg.Text(_t("main_gui.destination_folder")),
            sg.In(size=(25, 1), enable_events=True, key="-RESTORE-FOLDER-"),
            sg.FolderBrowse(),
        ],
        # Do not show which folder gets to get restored since we already make that selection
        #[sg.Text(_t("main_gui.only_include")), sg.Text(includes, size=(25, 1))],
        [sg.Button(_t("main_gui.restore"), key='restore'), sg.Button(_t("generic.cancel"), key="cancel")],
    ]

    layout = [[sg.Column(left_col, element_justification="C")]]
    window = sg.Window(_t("main_gui.restoration"), layout=layout, grab_anywhere=True, keep_on_top=False)
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, sg.WIN_CLOSE_ATTEMPTED_EVENT, "cancel"):
            break
        if event == "restore":
            action = {
                "action": "restore",
                "snapshot": snapshot_id,
                "target": values["-RESTORE-FOLDER-"],
                "restore-include": includes,
            }

            thread = _restore_window(action=action, config=config)
            while not thread.done() and not thread.cancelled():
                sg.PopupAnimated(loader_animation, message="{}...".format(_t("main_gui.restore_in_progress")), time_between_frames=50, background_color='darkgreen')
            sg.PopupAnimated(None)

            result = thread.result()
            if result:
                sg.Popup(_t("main_gui.restore_done"), keep_on_top=True)
            else:
                sg.PopupError(_t("main_gui.restore_failed"), keep_on_top=True)
            break
    window.close()


@threaded
def _gui_backup(action, config, stdout):
    return runner(action=action, config=config, verbose=True, stdout=stdout)  # We must use verbose so we get progress output from restic


def main_gui(config, config_file, version_string):
    backup_destination = _t('main_gui.local_folder')
    backend_type = None
    try:
        backend_type = config['repo']['repository'].split(':')[0].upper()
        if backend_type in ['REST', 'S3', 'B2', 'SFTP', 'SWIFT', 'AZURE', 'GZ', 'RCLONE']:
            backup_destination = "{} {}".format(_t('main_gui.external_server'), backend_type)
    except (KeyError, AttributeError, TypeError):
        pass

    right_click_menu = ["", [_t("generic.destination")]]

    layout = [
        [
            sg.Column(
                [
                    [sg.Text(OEM_STRING, font='Arial 14')],
                    [
                        sg.Column([
                            [sg.Image(data=OEM_LOGO)]
                        ], vertical_alignment="top"),
                        sg.Column([
                            [sg.Text("{}: ".format(_t('main_gui.backup_state')))],
                            [sg.Button(
                            _t("generic.unknown"),
                            key="state-button",
                            button_color=("white", "grey"),
                        )]
                            
                        ], vertical_alignment="top")
                    ],
                    [sg.Text("{} {}".format(_t('main_gui.backup_list_to'), backup_destination))],
                    [
                        sg.Listbox(
                            values=[], key="snapshot-list", size=(80, 15)
                        )
                    ],
                    [
                        sg.Button(_t('main_gui.launch_backup'), key='launch-backup'),
                        sg.Button(_t('main_gui.see_content'), key='see-content'),
                        sg.Button(_t('generic.configure'), key='configure'),
                        sg.Button(_t('generic.about'), key='about'),
                        sg.Button(_t("generic.quit"), key='exit'),
                    ],
                ],
                element_justification="C",
            )
        ]
    ]

    window = sg.Window(
        OEM_STRING,
        layout,
        default_element_size=(12, 1),
        text_justification="r",
        auto_size_text=True,
        auto_size_buttons=False,
        no_titlebar=False,
        grab_anywhere=False,
        keep_on_top=False,
        alpha_channel=0.9,
        default_button_element_size=(12, 1),
        right_click_menu=right_click_menu,
        finalize=True,
    )

    window.read(timeout=1)
    current_state, snapshot_list = get_gui_data(config)
    _gui_update_state(window, current_state, snapshot_list)
    while True:
        event, values = window.read(timeout=60000)

        if event in (sg.WIN_CLOSED, "exit"):
            break
        if event == "launch-backup":
            progress_windows_layout = [
                [sg.Multiline(size=(80, 10), key='progress', expand_x=True, expand_y=True)]
            ]
            progress_window = sg.Window(_t('main_gui.backup_activity'), layout=progress_windows_layout, finalize=True)
            # We need to read that window at least once fopr it to exist
            progress_window.read(timeout=1)
            stdout = queue.Queue()
            thread = _gui_backup(action={"action": "backup", "force": True}, config=config, stdout=stdout)
            while not thread.done() and not thread.cancelled():
                try:
                    stdout_line = stdout.get(timeout=.01)
                except queue.Empty:
                    pass
                else:
                    if stdout_line:
                        progress_window['progress'].Update(stdout_line)
                sg.PopupAnimated(loader_animation, message="{}...".format(_t('main_gui.backup_in_progress')), time_between_frames=50, background_color='darkgreen')
            sg.PopupAnimated(None)
            result = thread.result()
            current_state, snapshot_list = get_gui_data(config)
            _gui_update_state(window, current_state, snapshot_list)
            if not result:
                sg.PopupError(_t("main_gui.backup_failed"),
                keep_on_top=True)
            else:
                sg.Popup(_t("main_gui.backup_done"),
                keep_on_top=True)
            progress_window.close()
            continue
        if event == "restore-to":
            if not values["snapshot-list"]:
                sg.Popup(_t("main_gui.select_backup"), keep_on_top=True)
                continue
            restore_window(config, snapshot=values["snapshot-list"][0])
        if event == "see-content":
            if not values["snapshot-list"]:
                sg.Popup(_t("main_gui.select_backup"), keep_on_top=True)
                continue
            ls_window(config, snapshot=values["snapshot-list"][0])
        if event == "configure":
            config = config_gui(config, config_file)
        if event == _t("generic.destination"):
            try:
                if backend_type:
                    if backend_type in ['REST', 'SFTP']:
                        destination_string = config['repo']['repository'].split('@')[-1]
                    else:
                        destination_string = config['repo']['repository']
                sg.PopupNoFrame(destination_string)
            except (TypeError, KeyError):
                sg.PopupNoFrame(_t("main_gui.unknown_repo"))
        if event == 'about':
            _about_gui(version_string)

        # Update GUI on every window.read timeout = every minute or everytime an event happens, including the "uptodate" button
        current_state, snapshot_list = get_gui_data(config)
        _gui_update_state(window, current_state, snapshot_list)