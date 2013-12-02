import pprint
import sys
import os
import gc

import numpy as np
from audiolab import wavread, wavwrite

# First, loop over the entire track in couple-second chunks and take the mean
# of the signal -- amplitude. Then, attempt to categorize them, marking the smallest
# as a new track. Use more detail to determine exactly where the track begins, then
# add it to the track list and move to the next marked piece. Make sure tracks are
# longer than a certain length as well...

def get_amplitudes(d, samples_per_slice):
    # amplitudes data format: (start sample, end sample, mean between samples)
    amplitudes = []
    size = samples_per_slice
    loc_max = len(d) - size
    for loc in xrange(0, loc_max, size):
        amplitudes.append({'start': loc, 'end': loc + size, 'mean': np.mean(d[loc:(loc + size)])})
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

def find_interesting_deltas(d):
    # Interesting deltas are flat and low
    small_delta = 0.005
    small_amp = 0.01
    min_interest_distance = 60 * 44100
    interest = []
    for di in d:
        if abs(di['delta']) < small_delta and ((di['start_val'] + di['end_val']) / 2) < small_amp:
            if (len(interest) == 0 or interest[-1]['end_sample'] + min_interest_distance <= di['end_sample']):
                # Ignore early stuff, we'll have to trim the first track manually
                if (di['start_sample'] >= min_interest_distance):
                    start_sec = di['end_sample'] / 44100
                    #print "Found interesting period at time %02d:%02d" % (start_sec / 60, start_sec % 60)
                    interest.append(di)
    return interest

# Attempt to load and process the file
data, fs, enc = wavread(sys.argv[1])
datadir = sys.argv[1].replace('.wav', '')
if not os.path.exists(datadir):
    os.makedirs(datadir)
channel_sum = np.mean(data, 1)
mono_data = abs(channel_sum)

amps = get_amplitudes(mono_data, 44100)
track_pts = find_interesting_deltas(get_deltas(amps))
print "Found %d tracks." % (len(track_pts))

# Given the interesting points, binary search over the n seconds after them to locate
# the start of the next track.
min_sample_size = (44100 / 8)
lookahead = 44100 * 6
song_starts = []
for pt in track_pts:
    baseline_delta = 0.05
    baseline_val = 0.1
    #print "Finding track start for track at sample %d..." % (pt['start_sample'])
    end_sample = min(pt['end_sample'] + lookahead, len(mono_data))
    amps = get_amplitudes(mono_data[(pt['start_sample']):end_sample], min_sample_size)
    deltas = get_deltas(amps)
    # Take first delta bigger than some arbitrary baseline
    max_pt = None
    for d in deltas:
        if d['delta'] > baseline_delta:
            max_pt = d
            break;
    if (max_pt is None):
        max_pt = max([i for i in deltas if i['start_val'] < baseline_val], key=lambda x: x['delta'])
    # To do: adjust for zero-crossing? also, do we pull back for cueing purposes?
    pullback = 44100 / 4
    song_starts.append(pt['start_sample'] - pullback +
                       ((max_pt['start_sample'] + max_pt['end_sample']) / 2.0))

print "Found song starts:", song_starts

# Then, export
for i in xrange(len(song_starts)):
    filename = "%s/%03d.wav" % (datadir, i)
    if (i == 0):
        start = 0
        end = song_starts[i]
    elif (i == len(song_starts)):
        start = song_starts[i]
        end = len(data) - 1
    else:
        start = song_starts[i-1]
        end = song_starts[i]
    print "Writing file %s from %d to %d..." % (filename, start, end)
    wavwrite(data[start:end], filename, 44100)
