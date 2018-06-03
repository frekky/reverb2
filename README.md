reverb2
=======

Hello and welcome to reverb2, the ultimate in media conversion software
designed to work with Echo360!

You will need a working installation of `gnash` (GNU flash) and you
**must** be able to run the command `dump-gnash`. If you are having
difficulty finding it, I suggest you compile it yourself according to
https://stackoverflow.com/a/21023110

If you have difficulty building `gnash`, use:
./configure --enable-renderer=agg --enable-gui=dump --disable-menus --enable-media=ffmpeg --disable-jemalloc

Make sure `ffmpeg` is installed.

echoclone.py
------------

	echoclone.sh http://media.lcs.uwa.edu.au/echocontent | sqlite3 lectures.db

This parses the last ten days of presentation metadata and emits the SQL
commands to populate an easily searchable database. You should run it as
a cron job.

You can edit the script to list *every* presentation, but this is
usually slow and should be a once-off.)

echosearch.py
-------------

This is a CGI script ("web app", if you like) that expects to find a
`lectures.db` file and a writeable `playlist` directory in the same
directory as itself.

echoget.py
----------

	echoget.py <presentation.xml URL> [<output name>]

Output name may be unit code, for example.

This downloads all the nasty little SWF files that make up the videos
stored on LCS and turns them into a nice MPEG4 encoded file with both
projector streams displayed side-by-side. Audio is included.

For your convenience, the date of the lecture you are downloading is
suffixed to the output name provided, so you do not need to manually
check the date in the presentation.xml file.

Have fun!

License
-------

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
