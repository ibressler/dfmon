from PyQt4.QtCore import *
from PyQt4.QtGui import *

class MyTreeWidget(QTreeWidget):
    
    def __init__(s, parent=None):
        QTreeWidget.__init__(s, parent)
        # connect some signals/slots
        QObject.connect(
                        s, SIGNAL("customContextMenuRequested(const QPoint&)"), \
                        s.contextMenu)
        QMetaObject.connectSlotsByName(s)
    
    def sizeHint(s):
        """Show all columns (no horizontal scrollbar)"""
        widthHint = 0
        for col in range(0, s.columnCount()):
            colWidth = s.sizeHintForColumn(col)
            colWidth += 5
            s.header().resizeSection(col, colWidth)
            widthHint += colWidth + 2 # magic margin between columns
        widthHint += 2
        if not s.verticalScrollBar().isHidden():
            widthHint += s.verticalScrollBar().width()
        hint = QTreeWidget.sizeHint(s)
        hint.setWidth(widthHint)
        hint.setHeight(300)
        return hint
        
    def contextMenu(s, pos):
        item = s.itemAt(pos)
        print "item:", str(item.dev())
        menu = QMenu(s)
        testAction = QAction("blubb", menu)
        menu.addAction(testAction)
        # fix popup menu position
        pos = s.mapToGlobal(pos)
        pos.setY(pos.y() + s.header().sizeHint().height())
        menu.popup(pos)
