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


import itertools
import lxml.etree
import os
import os.path as path
import scipy.stats
import subprocess as sp
import sys
import tempfile
import urllib.parse


def info(*args, **kwargs):
    print('REVERB:', *args, **kwargs)


def nonidentical_tracks(tracks, track_file_dict):
    possible_pairs = itertools.combinations(tracks, 2)

    for pair in possible_pairs:
        if not all(x in tracks for x in pair): continue

        sizes = [[os.path.getsize(p) for p in track_file_dict[el]] for el in pair]

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


def pres2file(xml_url, out_path, careful=False):
    with tempfile.TemporaryDirectory(suffix='-reverb') as tmpdir:
        # chdir into our own temp directory (makes all the bash commands look nicer)
        out_path = path.realpath(out_path)
        swfcat_bin = path.join(path.dirname(path.realpath(__file__)), 'swfcat.sh')
        os.chdir(tmpdir)

        info('Input:', xml_url)
        info('Output:', out_path)

        if careful:
            info('Being --careful')

        if not out_path.endswith('.mp4'):
            info("Non-MP4 output file extension, probably won't work")

        # List all the SWFs that make up this presentation
        xml = lxml.etree.parse(xml_url)
        track_names = xml.xpath("//session-info/group[contains(@type,'projector')]/track[@type='flash-movie']/@directory")

        swf_remote_urls = {} # {track: [urls...], ...}
        for track in track_names:
            tag = xml.xpath("//session-info/group[contains(@type,'projector')]/track[@type='flash-movie' and @directory='%s']" % track)[0]
            filenames = tag.xpath("data/@uri")

            urls = [urllib.parse.urljoin(xml_url, track+'/'+fn) for fn in filenames]
            swf_remote_urls[track] = urls

        # Download SWFs, somewhat concurrently
        swf_local_paths = {} # {track: [paths...], ...}
        for track in track_names:
            groupdir = 'group-'+track
            os.mkdir(groupdir)
            urls = swf_remote_urls[track]
            info('Downloading', len(urls), 'SWFs to', groupdir)

            parallel_list = '\n'.join(urls + ['']).encode('ascii')
            sp.run(['parallel', '--will-cite', '-j10', 'wget', '-q', '{}'], input=parallel_list, cwd=groupdir, check=True)

            destfiles = [path.join(groupdir, url.split('/')[-1]) for url in urls]
            swf_local_paths[track] = destfiles

        # Check for and remove identical files
        if not careful:
            track_names = nonidentical_tracks(track_names, swf_local_paths)

        # Sort the tracks by size (live video on the right)
        track_totals = {}
        for track in track_names:
            size = sum(os.path.getsize(p) for p in swf_local_paths[track])
            track_totals[track] = size
        track_names = sorted(track_names, key=track_totals.get)

        # Guess where audio track is (not in xml!)
        audio_path = 'audio.mp3'
        audio_url = urllib.parse.urljoin(xml_url, audio_path)
        skip_secs = 0
        try:
            info('Downloading audio track')
            sp.run(['wget', '-q', audio_url], check=True)
            os.system('cp %s ~/' % audio_path)
        except:
            info('No audio track found at', audio_url)
            audio_path = None

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
            filelist_txt_file = 'group-%s.txt'%track
            with open(filelist_txt_file, 'w') as f:
                for p in paths:
                    print(p, file=f)

            # use swfcat.sh to dump-gnash a bunch of swfs as raw video on stdout
            swfcat_cmd = '{swfcat_bin} {swf_fps} {frames_per_swf} {bytes_per_frame} {filelist_txt_file}'.format(**locals())

            # then use bash process substitution to get that output into a named pipe, ready for ffmpeg to read
            dumper = '-f rawvideo -pix_fmt rgb32 -r {swf_fps} -s:v {swf_x}x{swf_y} -i file:<({swfcat_cmd})'.format(**locals())
            dumpers[track] = dumper

        # Requires bash because we use process substitution to capture swfcat's output
        # Confession: the old-timey pix_fmt and transcoding the audio track are for QT compatibility
        ffmpeg_cmd = ' '.join([
            'ffmpeg',
            '-hide_banner -nostdin',
            '-nostats -loglevel error', # comment to get progress
            '-y', # overwrite dest without asking
            *(dumpers[t] for t in track_names),
            ('-i %s -c:a aac -b:a 32k' % audio_path) if audio_path else '',
            ('-ss %f' % skip_secs) if skip_secs else '',
            ('-filter_complex:v hstack=inputs=%d:shortest=0' % len(track_names)) if len(track_names) > 1 else '',
            '-c:v libx264 -pix_fmt:v yuv420p -crf:v 26 -preset:v fast -tune:v stillimage',
            out_path,
        ])

        print(' FFMPEG COMMAND '.center(72, '-'))
        print(ffmpeg_cmd)
        print('-' * 72)
        sp.run(['bash', '-c', ffmpeg_cmd], check=True) # sh won't work


if __name__ == '__main__':
    args = sys.argv[1:]

    careful = False
    if args[0] == '--careful':
        del args[0]
        careful = True

    xml_url, out_path = args

    pres2file(xml_url, out_path, careful=careful)
