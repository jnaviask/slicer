import pprint
import sys
import os
import json
import argparse

import numpy as np
from audiolab import wavread, wavwrite

def get_amplitudes(d, samples_per_slice, shift_per_slice):
    # We will take overlapping samples if possible!
    amplitudes = []
    loc_max = len(d) - samples_per_slice
    shifts = samples_per_slice / shift_per_slice
    for loc in xrange(0, loc_max, shift_per_slice):
        amplitudes.append({'start': loc, 'end': loc + samples_per_slice,
                           'mean': np.mean(d[loc:(loc + samples_per_slice)])})
    return amplitudes

def get_deltas(amps):
    deltas = []
    for i in xrange(len(amps) - 1):
        deltas.append({
            'delta': amps[i+1]['mean'] - amps[i]['mean'],
            'start_val': amps[i]['mean'],
            'end_val': amps[i+1]['mean'],
            'start_sample': amps[i]['start'],
            'end_sample': amps[i+1]['end']
        })
    return deltas

def find_track_gaps(d):
    large_delta = 0.005
    small_delta = 0.005
    # Might want to remove large amp.
    large_amp = 0.008
    small_amp = 0.02
    min_interest_distance = 60 * 44100
    interest = []
    for i in xrange(len(d) - 1):
        gap = d[i]
        chg = d[i+1]
        if (abs(gap['delta']) < small_delta and chg['delta'] > large_delta and
            ((gap['start_val'] + gap['end_val']) / 2) < small_amp and
            chg['end_val'] > large_amp and
            ((len(interest) == 0 and
              gap['start_sample'] >= min_interest_distance) or
             (interest[-1]['end_sample'] + min_interest_distance <=
              gap['end_sample']))):
            interest.append(gap)
    return interest

def find_track_beginnings(d, gaps):
    song_starts = []
    for pt in gaps:
        song_starts.append(pt['end_sample'] - 22050)
    return song_starts

def load_audio_file(filename):
    data, fs, enc = wavread(filename)
    return data

def prepare_audio_file(data):
    channel_sum = np.mean(data, 1)
    mono_data = abs(channel_sum)
    return mono_data

def process_audio_file(mono_data):
    amps = get_amplitudes(mono_data, 44100 * 2, 44100 / 2)
    track_pts = find_track_gaps(get_deltas(amps))
    print "Found %d tracks." % (len(track_pts))
    song_starts = find_track_beginnings(mono_data, track_pts)
    return song_starts

def chop_audio_file(data, song_starts, save_dir):
    if not os.path.exists(save_dir):
        os.makrdirs(save_dir)
    for i in xrange(len(song_starts) + 1):
        filename = "%s/%03d.wav" % (save_dir, i)
        if (i == 0):
            start = 0
            end = song_starts[i]
        elif (i == len(song_starts)):
            start = song_starts[i-1]
            end = len(data) - 1
        else:
            start = song_starts[i-1]
            end = song_starts[i]
        print "Writing file %s: %02d:%02d to %02d:%02d..." % (
            filename,
            (start / 44100) / 60,
            (start / 44100) % 60,
            (end / 44100) / 60,
            (end / 44100) % 60)
        wavwrite(data[start:end], filename, 44100)

def save_song_starts(filename, song_starts):
    f = open(filename, 'w')
    json.dump(song_starts, f)
    f.close()

def load_song_starts(filename):
    f = open(filename, 'r')
    return json.load(f)

def get_song_starts_from_file(filename):
    data = load_audio_file(filename)
    mono_data = prepare_audio_file(data)
    starts = process_audio_file(mono_data)
    return starts

parser = argparse.ArgumentParser(description="chop vinyl-ripped audio files")
parser.add_argument("in-file", help="input audio file")
parser.add_argument("out-file",
                    help="output filename (for -d) or directory")
group = parser.add_mutually_exclusive_group()
group.add_argument("-d", "--detect",
                    help="detect track starts and write to file",
                    action="store_true")
group.add_argument("-c", "--chop", type=str,
                    help="chop file using given track start file")
args = parser.parse_args()
print args
