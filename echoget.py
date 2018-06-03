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


# Command-line utilities required:
# - bash
# - ffmpeg
# - gnu parallel
# - swftools
# - wget


import argparse
import contextlib
import datetime
import dateutil.parser
import hashlib
import itertools
import lxml.etree
import os
import os.path as path
import random
import re
import scipy.stats
import shlex
import string
import subprocess as sp
import sys
import tempfile
import urllib.parse


USERAGENT = random.choice([
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.79 Safari/537.36 Edge/14.14393"
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:53.0) Gecko/20100101 Firefox/53.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.79 Safari/537.36 Edge/14.14393',
    'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1)',
    'Mozilla/5.0 (Windows; U; MSIE 7.0; Windows NT 6.0; en-US)',
    'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.4506.2152; .NET CLR 3.5.30729)',
    'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.0; Trident/5.0;  Trident/5.0)',
    'Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.2; Trident/6.0; MDDCJS)',
    'Mozilla/5.0 (compatible, MSIE 11, Windows NT 6.3; Trident/7.0; rv:11.0) like Gecko',
    'Mozilla/5.0 (iPad; CPU OS 8_4_1 like Mac OS X) AppleWebKit/600.1.4 (KHTML, like Gecko) Version/8.0 Mobile/12H321 Safari/600.1.4',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1',
    'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)',
    'Mozilla/5.0 (Linux; Android 6.0.1; SAMSUNG SM-G570Y Build/MMB29K) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/4.0 Chrome/44.0.2403.133 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 5.0; SAMSUNG SM-N900 Build/LRX21V) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/2.1 Chrome/34.0.1847.76 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 6.0.1; SAMSUNG SM-N910F Build/MMB29M) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/4.0 Chrome/44.0.2403.133 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; U; Android-4.0.3; en-us; Galaxy Nexus Build/IML74K) AppleWebKit/535.7 (KHTML, like Gecko) CrMo/16.0.912.75 Mobile Safari/535.7',
    'Mozilla/5.0 (Linux; Android 7.0; HTC 10 Build/NRD90M) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.83 Mobile Safari/537.36',
])

DL_XATTR = 'user.reverb.origin'
SWFCAT_BIN = path.join(path.dirname(path.realpath(__file__)), 'swfcat.sh')


def info(*args, **kwargs):
    print('REVERB:', *args, **kwargs)


def nonidentical_tracks(tracks, track_file_dict):
    possible_pairs = itertools.combinations(tracks, 2)

    for pair in possible_pairs:
        if not all(x in tracks for x in pair): continue

        sizes = [[path.getsize(p) for p in track_file_dict[el]] for el in pair]

        pearsonr = scipy.stats.pearsonr(*sizes)[0] # really terrible abuse of this function
        rsq = pearsonr ** 2
        info('R-squared of', *pair, '=', rsq)

        if rsq > 0.85:
            sums = [sum(el) for el in sizes]
            if sums[0] < sums[1]:
                smallest = tracks[0]
            else:
                smallest = tracks[1]

            info('Deleting duplicate stream:', smallest)
            tracks = [t for t in tracks if t != smallest]

    return tracks


def how_much_leading_silence(audio_path):
    # snip a few silent seconds off the start of the video track
    silence_cmd = 'ffmpeg -i %s -af silencedetect=noise=-10dB:duration=1 -f null - 2>&1 | grep silencedetect | head -n2' % audio_path
    silence_data = os.popen(silence_cmd, 'r').read().lstrip().rstrip().split('\n')

    if len(silence_data) == 2:
        silence_start = float(silence_data[0].rpartition('silence_start: ')[2])
        silence_end = float(silence_data[1].rpartition('silence_end: ')[2].partition(' ')[0])

        if silence_start < 1 and silence_end < 60 * 60:
            return silence_end

    return 0


def get_prop(xml, prop):
    try:
        return xml.xpath('//session-info/%s/text()' % prop)[0].strip()
    except:
        return ''


def mkname(xml):
    # Date
    rawdate = xml.xpath('//session-info/presentation-properties/start-timestamp/text()')[0]
    rawdate = re.sub(r'([0-3][0-9])/([01][0-9])/((?:[12][0-9])[0-9][0-9])', r'\3-\2-\1', rawdate) # DD/MM/YYYY -> YYYY-MM-DD
    try:
        d = dateutil.parser.parse(rawdate, ignoretz=True)
    except ValueError:
        datestr = ''
    else:
        if d.minute >= 50:
            d += datetime.timedelta(minutes=60-d.minute)
        datestr = d.strftime('%Y-%m-%d %a %H%M')

    # Most important deets
    name = xml.xpath('//session-info/presentation-properties/name/text()')[0]
    desc = xml.xpath('//session-info/presentation-properties/description/text()')[0]

    # Try to get course code
    trash = name + ' ' + desc
    ucodechars = string.ascii_uppercase + string.digits + '-'
    trash = ''.join(c if c in ucodechars else ' ' for c in trash)
    ucodes = re.findall(r'\b[A-Z]{3,4}(?:-| )?[0-9]{3,4}\b', trash)
    ucodes = [x.replace('-', '').replace(' ', '') for x in ucodes]
    if ucodes:
        coursecode = max(ucodes, key=ucodes.count)
    else:
        coursecode = ''

    # Try to get meaningful title
    title = name
    title = re.sub(r'\S*_CR/([A-Z][A-Za-z]+)\S*', r'\1', title, flags=re.IGNORECASE)
    title = re.sub(r'\[repeat\]', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bsplus\b', '', title, flags=re.IGNORECASE)
    if coursecode:
        ucode_regex = re.sub(r'([A-Z])([0-9])', r'\1(?:-| )?\2', coursecode)
        title = re.sub(r'\b' + ucode_regex + r'(_\S+)?', '', title, flags=re.IGNORECASE)
    title = title.replace('/', '-')
    title = title.replace('()', '').replace('[]', '').replace('{}', '') # might have enclosed the above
    tostrip = ''.join(c for c in string.punctuation if c not in '()[]{}<>') + string.whitespace
    title = title.strip(tostrip)

    checkname = ' '.join([datestr, coursecode, title]).strip()
    checkname = ' '.join(checkname.split())
    checkname = checkname.replace('?', '').replace(':', '')
    checkname = checkname[:255 - len('.mp4')]

    return checkname


def mkfile_atomic(template):
    main, ext = path.splitext(template)

    idx = 1
    while True:
        if idx == 1:
            whole = main + ext
        else:
            whole = main + ' ' + str(idx) + ext

        try:
            open(whole, 'x').close()
        except FileExistsError:
            idx += 1
        else:
            break

    return whole


@contextlib.contextmanager
def close_when_done(path):
    try:
        fname = path.name
    except AttributeError:
        fname = path

    try:
        yield path
    finally:
        try:
            os.unlink(fname)
        except OSError:
            pass


def fail_if_already_downloaded(dest_dir, xml_url, exclude=None):
    for checkname in os.listdir(dest_dir):
        ext = path.splitext(checkname)[1].lower()
        if ext not in ('.m4v', '.mp4'): continue

        checkpath = path.join(dest_dir, checkname)
        if exclude and path.realpath(checkpath) == path.realpath(exclude): continue
        if not path.isfile(checkpath): continue

        try:
            with open(checkpath, 'rb') as f:
                f.seek(-4096, os.SEEK_END)
                metadata = f.read()
        except:
            continue

        metadata = metadata.replace(b'https://', b'http://')
        norm_url = xml_url.encode('ascii').replace(b'https://', b'http://')

        if norm_url in metadata:
            raise FileExistsError('%r matches' % checkpath)


def urlhash(url):
    return hashlib.sha1(url.replace('https://', 'http://').encode('ascii')).hexdigest()


def pres2file(xml_url, dest_suggestion='', careful=False, short=False):
    if path.isdir(dest_suggestion):
        dest_dir = dest_suggestion.rstrip('/')
    else:
        dest_dir = path.dirname(dest_suggestion)

    if not xml_url.endswith('.xml'):
        xml_url = xml_url.rstrip('/') + '/presentation.xml'
    info('Input:', xml_url)

    # Hash the "canonical" URL and create a so-named file exclusively, for while we're downloading
    progresspath = path.join(dest_dir, '.dl-' + urlhash(xml_url))
    with close_when_done(open(progresspath, 'x')) as progressfile:
        print(xml_url, file=progressfile)
        progressfile.flush()

        # Check again now that we have created our file
        fail_if_already_downloaded(dest_dir, xml_url)

        xml = lxml.etree.fromstring(sp.run(['curl', '--user-agent', '"'+USERAGENT+'"', '-s', xml_url], check=True, stdout=sp.PIPE).stdout)

        if path.isdir(dest_suggestion):
            dest_name = mkname(xml)
        else:
            dest_name = path.basename(dest_suggestion)

        if dest_name.lower().endswith('.mp4'):
            dest_name = dest_name[:-4]

        tmpdest = mkfile_atomic(path.join(dest_dir, dest_name + ' INCOMPLETE.mp4'))
        info('Temp output:', tmpdest)

        with tempfile.TemporaryDirectory(suffix='-reverb') as tmpdir, close_when_done(tmpdest):
            # List all the SWFs that make up this presentation
            track_names = xml.xpath("//session-info/group[contains(@type,'projector')]/track[@type='flash-movie']/@directory")

            swf_remote_urls = {} # {track: [urls...], ...}
            for track in track_names:
                tag = xml.xpath("//session-info/group[contains(@type,'projector')]/track[@type='flash-movie' and @directory='%s']" % track)[0]
                filenames = tag.xpath("data/@uri")

                urls = [urllib.parse.urljoin(xml_url, track+'/'+fn) for fn in filenames]
                if short:
                    del urls[4:]
                swf_remote_urls[track] = urls

            # Download SWFs, somewhat concurrently
            swf_local_paths = {} # {track: [paths...], ...}
            for track in track_names:
                groupdir = path.join(tmpdir, 'group-'+track)
                os.mkdir(groupdir)
                urls = swf_remote_urls[track]
                info('Downloading', len(urls), 'SWFs to', groupdir)

                parallel_list = '\n'.join(urls + ['']).encode('ascii')
                sp.run(['parallel', '--will-cite', '-j10', 'curl', '--user-agent', '"'+USERAGENT+'"', '-s', '-o', '{/}', '{}'], input=parallel_list, cwd=groupdir, check=True)

                destfiles = [path.join(groupdir, url.split('/')[-1]) for url in urls]
                swf_local_paths[track] = destfiles

            # Check for and remove identical files
            if not careful:
                track_names = nonidentical_tracks(track_names, swf_local_paths)

            # Sort the tracks by size (live video on the right)
            track_totals = {}
            for track in track_names:
                size = sum(path.getsize(p) for p in swf_local_paths[track])
                track_totals[track] = size
            track_names = sorted(track_names, key=track_totals.get)

            # Guess where audio track is (not in xml!)
            audio_path = 'audio.mp3'
            audio_url = urllib.parse.urljoin(xml_url, audio_path)
            skip_secs = 0
            try:
                info('Downloading audio track')
                sp.run(['curl', '--user-agent', USERAGENT, '-s', '-o', audio_path, audio_url], cwd=tmpdir, check=True)
            except:
                info('No audio track found at', audio_url)
                audio_path = None
            else:
                audio_path = path.join(tmpdir, audio_path)

            # Skip leading silence
            skip_secs = 0
            if audio_path and not careful:
                skip_secs = how_much_leading_silence(audio_path)
            if skip_secs:
                info('Skipping', skip_secs, 'sec of silence')

            # Crafting the perfect bash command: a master class
            # List of strings to put in the ffmpeg command line, one per stream.
            # Just to be very clear, the following code block does no video processing.
            # It just prepares the ffmpeg command.
            dumpers = {}
            for track in track_names:
                paths = swf_local_paths[track]

                # get some vital statistics from the first swf
                firstswf = paths[0]
                args = ['-r', '-X', '-Y']
                vals = (sp.run(['swfdump', arg, firstswf], check=True, stdout=sp.PIPE).stdout.decode('ascii').rstrip().split()[-1] for arg in args)
                vals = (int(float(x)) for x in vals)
                swf_fps, swf_x, swf_y = vals
                bytes_per_frame = swf_x * swf_y * 4

                # get frames-per-SWF from the XML (not from the SWF iteself, because SWFs usually have one extra frame, which wrecks the timing)
                fctag = xml.xpath("//session-info/group[contains(@type,'projector')]/track[@type='flash-movie' and @directory='%s']/data/@duration" % track)[0]
                frames_per_swf = int(fctag) * swf_fps // 1000

                # one of the args to swfcat.sh: a text file containing a list of swf paths
                filelist_txt_file = path.join(tmpdir, 'group-%s.txt'%track)
                with open(filelist_txt_file, 'w') as f:
                    for p in paths:
                        print(p, file=f)

                # use swfcat.sh to dump-gnash a bunch of swfs as raw video on stdout
                swfcat_cmd = [shlex.quote(SWFCAT_BIN), swf_fps, frames_per_swf, bytes_per_frame, filelist_txt_file]
                swfcat_cmd = ' '.join(str(x) for x in swfcat_cmd)

                # then use bash process substitution to get that output into a named pipe, ready for ffmpeg to read
                dumper = '-f rawvideo -pix_fmt rgb32 -r {swf_fps} -s:v {swf_x}x{swf_y} -i file:<({swfcat_cmd})'.format(**locals())
                dumpers[track] = dumper

            # Stuff all the metadata we know into a freeform comment (because it's all crap anyway)
            comment = [
                ('Source URL', xml_url),
                ('Original Name', get_prop(xml, 'presentation-properties/name')),
                ('Original Description', get_prop(xml, 'presentation-properties/description')),
                ('Original Location', get_prop(xml, 'presentation-properties/location')),
                ('Original Timestamp', get_prop(xml, 'presentation-properties/start-timestamp')),
                ('Original Presenter', get_prop(xml, 'presenter-properties/name')),
            ]
            comment = '\n'.join('%s: %s' % (k, v) for (k, v) in comment)

            # Requires bash because we use process substitution to capture swfcat's output
            # Confession: the old-timey pix_fmt and transcoding the audio track are for QT compatibility
            ffmpeg_cmd = ' '.join([
                'ffmpeg',
                '-hide_banner -nostdin',
                '-nostats -loglevel error', # comment to get progress
                '-y', # overwrite dest without asking
                *(dumpers[t] for t in track_names),
                ('-i %s -c:a aac -b:a 32k' % audio_path) if audio_path else '',
                '-map_metadata -1 -metadata comment=' + shlex.quote(comment), # strip metadata from input files
                ('-ss %f' % skip_secs) if skip_secs else '',
                ('-filter_complex:v hstack=inputs=%d:shortest=0' % len(track_names)) if len(track_names) > 1 else '',
                '-c:v libx264 -pix_fmt:v yuv420p -crf:v 26 -preset:v fast -tune:v stillimage',
                shlex.quote(tmpdest),
            ])

            print(' FFMPEG COMMAND '.center(72, '-'))
            print(ffmpeg_cmd.replace('\n', '<newline>'))
            print('-' * 72)
            sp.run(['bash', '-c', ffmpeg_cmd], check=True) # sh won't work

            finaldest = mkfile_atomic(path.join(dest_dir, dest_name + '.mp4'))
            info('Final output:', finaldest)
            os.rename(tmpdest, finaldest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', '-o', action='store', default='', type=path.realpath, metavar='PATH', help='Destination file or directory')
    parser.add_argument('--careful', action='store_true', help='Omit silence-skipping and duplicate stream thinning')
    parser.add_argument('--short', action='store_true', help='[debug] Save only a few minutes')
    parser.add_argument('url', action='store', metavar='URL', help='Presentation URL')
    args = parser.parse_args()

    pres2file(args.url, args.out, careful=args.careful, short=args.short)
