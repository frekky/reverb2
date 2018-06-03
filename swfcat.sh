#!/bin/sh

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
