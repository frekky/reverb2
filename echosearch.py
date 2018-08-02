#!/usr/bin/env python3

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


from html import escape as esc
import cgi
import cgitb; cgitb.enable()  # for troubleshooting
import datetime
import dateutil.parser
import hashlib
import html
import os.path
import re
import sqlite3
import sys


RE_UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
DB = os.path.join(os.path.dirname(__file__), 'lectures.db')
PLAYLIST = os.path.join(os.path.dirname(__file__), 'playlist')


def mangle_location(x):
    a, b, c = x.partition(':')
    if len(a) < len(c):
        x = c.lstrip()

    a, b, c = x.partition('[')
    if len(a) > len(c):
        x = a.rstrip()

    a, b, c = x.partition(',')
    if a == a.upper() and len(c) >= 5:
        x = c.lstrip()

    for w in ['Lecture Theatre', 'Lecture Theatre', 'Lecture Hall', 'Lecture Room', 'Seminar Room']:
        rp = ''.join(wd[0] for wd in w.split())
        x = x.replace(w, rp)

    x = esc(x)

    if len(x.split(' ')) == 2:
        x = x.replace(' ', '&nbsp;')

    return x


def mangle_date(x):
    d = dateutil.parser.parse(x, ignoretz=True)
    d += datetime.timedelta(minutes=30)
    x = d.strftime('%a %d/%m/%y %I%p')
    x = x.replace(' 0', ' ')
    x = esc(x)
    x = x.replace(' ', '&nbsp;')
    return x


def urlhash(url):
    return hashlib.sha1(url.replace('https://', 'http://').encode('ascii')).hexdigest()


def add_to_playlist(url):
    os.makedirs(PLAYLIST, exist_ok=True)

    the_hash = urlhash(url)

    n = 1
    while True:
        tmpfile = os.path.join(PLAYLIST, '%s-%d~' % (the_hash, n))
        try:
            with open(tmpfile, 'x') as f:
                print(url, file=f)
        except FileExistsError:
            n += 1
        else:
            break

    fname = os.path.join(PLAYLIST, the_hash)

    os.rename(tmpfile, fname)


# def remove_from_playlist(url):
#     os.makedirs(PLAYLIST, exist_ok=True)

#     the_hash = urlhash(url)

#     fname = os.path.join(PLAYLIST, the_hash)

#     try:
#         os.unlink(fname)
#     except FileNotFoundError:
#         pass


def list_playlist(and_delete=False):
    os.makedirs(PLAYLIST, exist_ok=True)

    the_list = [os.path.join(PLAYLIST, fname) for fname in os.listdir(PLAYLIST) if not fname.endswith('~')]
    the_list.sort(key=os.path.getmtime)
    the_list.reverse()

    for path in the_list:
        try:
            with open(path, 'r') as f:
                for l in f.readlines():
                    yield l.rstrip()
            if and_delete:
                os.unlink(path)
        except FileNotFoundError:
            pass


# Okay, generate a page...

# questions:
# HTML or RSS? (or should I use Atom?)
# Search query? Full listing? Feed listing?


form = cgi.FieldStorage()



if os.getenv('REQUEST_METHOD') == 'POST':
    print('Content-type: text/html')
    print()

    for url in form.getlist('sel'):
        add_to_playlist(url)

    print('<!DOCTYPE html>')
    print('<meta charset="utf-8">')
    print('<script>window.history.back();</script>')
    print('<p>Added %s URLs to playlist. You don\'t have JavaScript, so navigate back to the search page manually.' % len(url_list))

    exit()




if 'rawplaylist' in form:
    print('Content-type: text/plain')
    print()

    for url in list_playlist(and_delete=('delete' in form)):
        print(url)

    exit()



# QUERY
# well... this is slightly tricky. I probably need to 

QSTART = 'SELECT url, date, minutes, name, description, location, presenter_name FROM lectures '
QEND = ' ORDER BY date DESC'

conn = sqlite3.connect(DB)
curs = conn.cursor()

err = ''

if 'q' in form:
    like = '%' + form.getfirst('q') + '%'
    curs.execute(QSTART + 'WHERE name LIKE ? OR description LIKE ? OR location LIKE ? OR presenter_name LIKE ?' + QEND, (like, like, like, like)) # fix this up later!
else:
    curs.execute(QSTART + QEND)




if 'raw' in form:
    # HTTP HEADERS (do this before anything can fail!)

    print('Content-type: text/plain')
    print()

    for rec in iter(curs.fetchone, None):
        url, date, minutes, name, description, location, presenter_name = rec

        print(url)


else:
    # HTTP HEADERS (do this before anything can fail!)

    print('Content-type: text/html')
    print()


    # PALAVER

    print('<!DOCTYPE html>')
    print('<meta charset="utf-8">')
    print('<title>Echo Search</title>')


    # JAVASCRIPT

    print('''
    <script>
        function checkAll(x) {
            var allInputs = document.getElementsByTagName("input");
            for (var i = 0; i < allInputs.length; i++) {
                if (allInputs[i].type == "checkbox") {
                    allInputs[i].checked = x;
                }
            }
        }
    </script>
    ''')


    # SEARCH FORM

    print('<section>')
    print('<h1>Search</h1>')

    print('<form>')
    print('<input type="text" name="q" value="%s">' % esc(form.getfirst('q', '')))
    print('<input type="submit" value="Search">')
    print('<input type="submit" name="raw" value="Show Raw URLs">')
    print('</form>')

    print('</section>')


    # ACTIONS

    print('<section>')
    print('<h1>Actions</h1>')

    print('<form id="selection" method="post"></form>')
    print('<script>document.write(\'<input type="button" form="selection" value="Select All" onclick="checkAll(true)"> <input type="button" form="selection" value="Select None" onclick="checkAll(false)">\');</script>')
    print('<input type="submit" form="selection" value="Add Selection to Playlist">')
    print('<span><a href="%s">Raw playlist</a></span> <span><a href="%s">Clear playlist</a></span>' % (os.path.basename(__file__) + '?rawplaylist=1', os.path.basename(__file__) + '?rawplaylist=1&delete=1'))

    print('</section>')


    # ERROR

    if err:
        print('<p>' + esc(err))
        exit()


    # OUTPUT TABLE

    print('<section>')
    print('<h1>Results</h1>')

    print('<table>')
    print('<tbody>')

    for rec in iter(curs.fetchone, None):
        url, date, minutes, name, description, location, presenter_name = rec

        print(
            '<tr>' + 
            '<td><input type="checkbox" form="selection" name="sel" value="%s">'%url + 
            '<td>' + mangle_date(date) + '<br>' + '%d min'%minutes + '<br>' + mangle_location(location) +
            '<td>' +
                '<strong>' + esc(name) + '</strong>'
                '<br>Description: ' + esc(description) +
                '<br>Presenter: ' + esc(presenter_name) +
                '<br>URL: ' + esc(url)
        )
