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


TENDAYS=10
export USERAGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.79 Safari/537.36 Edge/14.14393" # Edge


if [ $# -eq 0 ]
then
	echo THE ECHO360 DATABASE RIPPER >&2
	echo Copy metadata from a listable Echo360 directory tree to a SQLite db. >&2
	echo >&2
	echo -e "Usage:\t$0" "[-f|--full] ECHOURL | sqlite3 DATABASE" >&2
	echo -e \\tIf --full is not passed, only the last $TENDAYS days are databased. >&2
	echo -e \\tYou can use file: URLs, but they will end up in the database. >&2
	exit 1
fi

if [[ $1 =~ ^-?-f(ull)?$ ]]
then
	FULL=1; shift
fi

ECHOURL="`echo "$1" | sed 's!/*$!!'`/" # force the trailing slash!

export TMPDIR=`mktemp -d --suffix=-reverb2`


function quot {
	echo -n "'"
	(cat; echo -n "$@") | sed "s/'/''/g"
	echo -n "'"
}
export -f quot


function xpath {
	xmllint --xpath "$2" "$1" | perl -MHTML::Entities -pe 'decode_entities($_);' | iconv -f utf8 -t ascii//TRANSLIT # in case of awful surprises
}
export -f xpath


function fixDate {
	# pass in a crazy echo date like "17/11/2017 4:01:00 PM"
	# i will ISO-ify it enough that GNU date can read it
	badDate="$1"
	if [ ! -z "${badDate// }" ]
	then
		badDate="`echo "$badDate" | sed 's!\([0-3][0-9]\)/\([01][0-9]\)/\([12][0-9][0-9][0-9]\)!\3-\2-\1!'`"
		date --iso-8601=minutes -d "$badDate"
	fi
}
export -f fixDate


function dayDirsFromDayOffsets {
	# Ugh date math. Perl easier than juggling between BSD and GNU date(1).
	perl -MPOSIX=strftime -lne 'print strftime("%y%V/%u/",localtime(time()+86400*$_))' | sed "s!^!$1!"
}


function guessEveryDayDir {
	listDir "$1" | grep '/[0-9]\{4\}/$' |
	while read line
	do
		seq -f "$line%g/" 7
	done
}


function listDir {
	if [[ $1 =~ ^file: ]]
	then
		unixpath="`echo "$1" | sed 's!file:/*!/!'`"
		ls -p "$unixpath" 2>/dev/null | grep / |
		sed "s!^!$1!"
	else
		curl --user-agent "$USERAGENT" -s "$1" | grep /icons/folder.gif | 
		sed 's!.*href="!!' | # strip to left of href attr
		sed 's!".*!!' | # strip to right
		sed "s!^!$1!" # make listDir x return x/children
	fi
}
export -f listDir


function getXML {
	URL="$1presentation.xml"
	T="$TMPDIR/`basename "$1"`.xml"

	curl --fail --user-agent "$USERAGENT" -s -o "$T" "$URL" || return

	# Hack: fix-up special characters in XML, expecially stray nbsp
	iconv -f utf8 -t ascii//TRANSLIT "$T" > "$T.2"
	xmllint --noblanks "$T.2" | sed 's/> </></' > "$T"
	rm -f "$T.2"

	echo "$T" "$URL"
}
export -f getXML


function parseXML {
	T="`echo "$1" | sed 's/ .*//'`"
	URL="`echo "$1" | sed 's/.* //'`"

	(
	# Ugh datemath. Get the start time in a sane format.
	lec_start="`xpath "$T" "//session-info/presentation-properties/start-timestamp/text()"`"
	lec_end="`xpath "$T" "//session-info/presentation-properties/end-timestamp/text()"`"

	lec_start="`fixDate "$lec_start"`"
	lec_end="`fixDate "$lec_end"`"

	# And the length in minutes of the recording (also ugly!)
	lec_mins=0
	if [ ! -z "$lec_start" ] && [ ! -z "$lec_end" ]
	then
		lec_mins=$((`date -d "$lec_end" "+%s"` - `date -d "$lec_start" "+%s"`))
		lec_mins=$((lec_mins / 60))
	fi

	tr '\n' ' ' <<-HERE
	REPLACE INTO "lectures" VALUES (
		`quot "$URL"`,
		`xpath "$T" "//session-info/presentation-properties/guid/text()" | quot`,
		`quot "$lec_start"`,
		$lec_mins,
		`xpath "$T" "//session-info/presentation-properties/name/text()" | quot`,
		`xpath "$T" "//session-info/presentation-properties/description/text()" | quot`,
		`xpath "$T" "//session-info/presentation-properties/location/text()" | quot`,
		`xpath "$T" "//session-info/presenter-properties/name/text()" | quot`,
		`xpath "$T" "//session-info/presenter-properties/email/text()" | quot`
	);
HERE
	echo

	rm -f "$T"
	) 2> >(grep -v "XPath set is empty" >&2)
}
export -f parseXML


# echo "BEGIN TRANSACTION;"

tr '\n' ' ' <<-HERE
	CREATE TABLE IF NOT EXISTS "lectures" (
		url TEXT PRIMARY KEY,
		declared_uuid TEXT,
		date TEXT,
		minutes INT,
		name TEXT,
		description TEXT,
		location TEXT,
		presenter_name TEXT,
		presenter_email TEXT
	);
HERE

if [ ! -z $FULL ]
then
	guessEveryDayDir "$ECHOURL"
else
	seq -$TENDAYS 1 | dayDirsFromDayOffsets "$ECHOURL"
fi |
parallel --will-cite -j20 listDir | parallel --will-cite -j20 getXML | parallel --will-cite -j20 parseXML

# echo "COMMIT;"

rm -rf "$TMPDIR"
