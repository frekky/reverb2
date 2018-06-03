#!/bin/sh

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


# USAGE: swfcat.sh FRAMERATE FRAMES BYTES_PER_FRAME URL_LIST_FILE > RAWVIDEO

# careful: spits out a lot of data

set -e

FRAMERATE="$1"
FRAMES="$2"
BYTES_PER_FRAME="$3"
URL_LIST_FILE="$4"

while read SWF
do
	mkfifo "$SWF.rawfifo"
	dump-gnash -D "$SWF.rawfifo@$FRAMERATE" -1 "$SWF" > /dev/null &
	#gnashpid=$!
	cat "$SWF.rawfifo" /dev/zero | head --bytes=$(($BYTES_PER_FRAME * $FRAMES))
	#wait $gnashpid
	rm -f "$SWF.rawfifo"
done < "$URL_LIST_FILE"
