"""Module docstring.

This serves as a long usage message.
"""

import sys
import getopt

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg

def main(argv=None):
    if argv is None:
        argv = sys.argv
#    try:
    try:
        opts, args = getopt.getopt(argv[1:], "h", ["help"])
        print "opts:", opts, "args:", args
    except getopt.error, msg:
         raise Usage(msg)
#    except Usage, err:
#        print >>sys.stdout, err.msg
#        print >>sys.stdout, "for help use --help"
#        return 2

if __name__ == "__main__":
    sys.exit(main())
