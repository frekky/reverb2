#!/bin/bash

# Copyright (C) 2018 Frekk van Blagh et al.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


export LOCALBASE="$1"
export ECHOBASE=http://media.lcs.uwa.edu.au/echocontent

function dirFromDeltaDays {
	# Ugh date math. Perl easier than juggling between BSD and GNU date(1).
	perl -MPOSIX=strftime -lne 'print strftime("%y%V/%u",localtime(time()+86400*$_))'
}

function everyDir {
	listDir "" | grep '[0-9]\{4\}' |
	while read line
	do
		seq -f "$line/%g" 7
	done
}

function listDir {
	wget -q -O - "$ECHOBASE/$1" | grep /icons/folder.gif | 
	sed 's!.*href="!!' | # strip to left of href attr
	sed 's!/".*!!' | # strip to right
	sed "s!^!$1/!" | # make listDir x return x/children
	sed 's!^/!!' # strip leading slash, just in case
}
export -f listDir

function pullDir {
	mkdir -p "$LOCALBASE/$1"
	cd "$LOCALBASE/$1"
	wget -q --timestamping "$ECHOBASE/$1/presentation.xml"
}
export -f pullDir

function listAndPull {
	parallel --will-cite listDir | parallel --will-cite pullDir
}

if [ -d "$LOCALBASE" ]
then
	echo "Incremental mode (going back 10 days)"
	seq -10 1 | dirFromDeltaDays | listAndPull
else
	echo "Initial clone"
	mkdir -p "$LOCALBASE"
	everyDir | listAndPull
fi