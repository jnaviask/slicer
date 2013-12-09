import pprint
import sys
import os
import json
import argparse

import numpy as np
import scipy.io.wavfile as sp

def samples_to_string(samples, rate, usems=False):
    minutes = (st / rate) / 60
    seconds = (st / rate) % 60
    if (usems):
        ms = ((st % rate) / (rate / 1000.))
        return "%d:%02d:%03d" % (minutes, seconds, ms)
    else:
        return "%d:%02d" % (minutes, seconds)
        
def string_to_samples(s, rate):
    items = s.split(":")
    minutes = int(items[0])
    seconds = int(items[1], base=10)
    if (len(items) == 3):
        ms = int(times[2])
        return (minutes * rate * 60) + (seconds * rate) + int(ms * (rate / 1000.))
    else:
        return (minutes * rate * 60) + (seconds * rate)

def get_amplitudes(d, rate, samples_per_slice, shift_per_slice):
    samples_per_slice = int(samples_per_slice * rate)
    shift_per_slice = int(shift_per_slice * rate)
    loc_max = len(d) - samples_per_slice
    shifts = samples_per_slice / shift_per_slice
    amplitudes = []
    for loc in xrange(0, loc_max, shift_per_slice):
        sample = abs(np.mean((d[loc:(loc + samples_per_slice)]), 1))
        amplitudes.append({'start': loc, 'end': loc + samples_per_slice,
                           'mean': np.mean(sample)})
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
    large_delta = 300
    small_delta = 300
    small_amp = 800
    min_interest_distance = 60 * 44100
    interest = []
    for i in xrange(len(d) - 1):
        gap = d[i]
        chg = d[i+1]
        if (abs(gap['delta']) < small_delta and chg['delta'] > large_delta and
            ((gap['start_val'] + gap['end_val']) / 2) < small_amp and
            ((len(interest) == 0 and
              gap['start_sample'] >= min_interest_distance) or
             (interest[-1]['end_sample'] + min_interest_distance <=
              gap['end_sample']))):
            interest.append(gap)
    final_sample = d[-1]['end_sample']
    if (final_sample - interest[-1]['end_sample'] < min_interest_distance):
        interest = interest[:-1]
    return interest

def process_audio_file(data, rate):
    amps = get_amplitudes(data, rate, 1, 0.5)
    deltas = get_deltas(amps)
    track_pts = find_track_gaps(deltas)
    print "Found %d songs." % (len(track_pts) + 1)
    #pprint.pprint(track_pts)
    pullback = rate / 2
    song_starts = [i['end_sample'] - pullback for i in track_pts]
    return song_starts

def chop_audio_file(data, rate, song_starts, save_dir):
    # Last item in song_starts should be the end of the last file
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    for i in xrange(len(song_starts) + 1):
        filename = "%s/%03d.wav" % (save_dir, i)
        if (i == 0):
            start = 0
            end = song_starts[i]
        elif (i < len(song_starts)):
            start = song_starts[i-1]
            end = song_starts[i]
        else:
            start = song_starts[-1]
            end = len(data)
        print "Writing file %s:%s to %s..." % (filename,
            samples_to_string(state, rate), samples_to_string(end, rate))
        sp.write(filename, rate, data[start:end])

def save_song_starts(filename, rate, song_starts):
    start_strings = [samples_to_string(st, rate, usems=True) for st in song_starts]
    f = open(filename, 'w')
    json.dump(start_strings, f)
    f.close()

def load_song_starts(filename, rate):
    f = open(filename, 'r')
    start_strs = json.load(f)
    f.close();
    starts = [string_to_samples(s) for s in start_strs]
    return starts

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="slice vinyl rips into individual tracks")
    parser.add_argument("infile", help="input audio file")
    parser.add_argument("outfile",
                        help="output filename (for -d) or directory")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-d", "--detect",
                       help="detect track starts and write to file",
                       action="store_true")
    group.add_argument("-c", "--chop", type=str,
                       metavar="slice-file",
                       help="chop file using given track start file")
    args = parser.parse_args()

    (rate, data) = sp.read(args.infile, mmap=True)
    if args.detect:
        starts = process_audio_file(data, rate)
        save_song_starts(args.outfile, rate, starts)
    elif args.chop is not None:
        starts = load_song_starts(args.chop, rate)
        chop_audio_file(data, rate, starts, args.outfile)
    else:
        starts = process_audio_file(data)
        chop_audio_file(data, rate, starts, args.outfile)
