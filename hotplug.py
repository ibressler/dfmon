"""Module docstring.

This serves as a long usage message.
"""

import sys
import os
import getopt

# todo:
    # truecrypt compatibility

from hotplugCmd import consoleMenu
from hotplugQt import qtMenu


class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg

def cmdName(argv):
    if not argv or len(argv) <= 0:
        return ""
    else:
        return os.path.basename(argv[0])

def showUsage(argv):
    msg = cmdName(argv)+": Does not support options atm, sry."
    return msg

def main(argv=None):
    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], "hc", ["help", "console"])
        except getopt.error, msg:
             raise Usage(msg)
    except Usage, err:
        print >>sys.stderr, err.msg
        print >>sys.stderr, cmdName(argv)+": For help use --help"
        return 2
#    print "opts:", opts, "args:", args
#    print "test:", unicode("-h")
    if (unicode("-h"), "") in opts:
        print >>sys.stdout, showUsage(argv)
        return 0
    elif (unicode("-c"), "") in opts:
        return consoleMenu()
    else:
        return qtMenu(argv)

if __name__ == "__main__":
    sys.exit(main())
