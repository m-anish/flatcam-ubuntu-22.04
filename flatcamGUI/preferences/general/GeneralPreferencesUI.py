from PyQt5 import QtWidgets
from PyQt5.QtCore import QSettings

from flatcamGUI.preferences.general.GeneralAppPrefGroupUI import GeneralAppPrefGroupUI
from flatcamGUI.preferences.general.GeneralAPPSetGroupUI import GeneralAPPSetGroupUI
from flatcamGUI.preferences.general.GeneralGUIPrefGroupUI import GeneralGUIPrefGroupUI

import gettext
import FlatCAMTranslation as fcTranslate
import builtins

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext

settings = QSettings("Open Source", "FlatCAM")
if settings.contains("machinist"):
    machinist_setting = settings.value('machinist', type=int)
else:
    machinist_setting = 0


class GeneralPreferencesUI(QtWidgets.QWidget):
    def __init__(self, decimals, parent=None):
        QtWidgets.QWidget.__init__(self, parent=parent)
        self.layout = QtWidgets.QHBoxLayout()
        self.setLayout(self.layout)
        self.decimals = decimals

        self.general_app_group = GeneralAppPrefGroupUI(decimals=self.decimals)
        self.general_app_group.setMinimumWidth(250)

        self.general_gui_group = GeneralGUIPrefGroupUI(decimals=self.decimals)
        self.general_gui_group.setMinimumWidth(250)

        self.general_app_set_group = GeneralAPPSetGroupUI(decimals=self.decimals)
        self.general_app_set_group.setMinimumWidth(250)

        self.layout.addWidget(self.general_app_group)
        self.layout.addWidget(self.general_gui_group)
        self.layout.addWidget(self.general_app_set_group)

        self.layout.addStretch()
