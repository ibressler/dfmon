"""Qt GUI for the hotplug manager
"""

import sys
from PyQt4 import QtCore, QtGui
from mainwindow import Ui_MainWindow

class MainWindow(QtGui.QMainWindow, Ui_MainWindow):

    def __init__(s, parent=None):
        QtGui.QMainWindow.__init__(s, parent)
#        s.ui = Ui_Form1()
        s.setupUi(s)

def show(argv):
    app = QtGui.QApplication(argv)
    mw = MainWindow()
    mw.show()
    return app.exec_()
