from PyQt4.QtGui import *

class MyTreeWidget(QTreeWidget):
    
    def __init__(s, parent=None):
        QTreeWidget.__init__(s, parent)
    
    def sizeHint(s):
        widthHint = 0
        for col in range(0, s.columnCount()):
            colWidth = s.sizeHintForColumn(col)
            colWidth += 5
            s.header().resizeSection(col, colWidth)
            widthHint += colWidth + 2 # magic margin between columns
        if not s.verticalScrollBar().isHidden():
            widthHint += s.verticalScrollBar().width()
        hint = QTreeWidget.sizeHint(s)
        hint.setWidth(widthHint)
        return hint
