#!/bin/sh

MYCMD=$0
MYPATH=$(pwd)/${MYCMD%/*}
LD_LIBRARY_PATH=$MYPATH $MYPATH/dfmon
