import pprint
import sys
import os
import json
import argparse

import numpy as np
import scipy.io.wavfile as sp

verbose = True

def samples_to_string(samples, rate, usems=False):
    minutes = (samples / rate) / 60
    seconds = (samples / rate) % 60
    if (usems):
        ms = ((samples % rate) / (rate / 1000.))
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

def find_gaps(amps, num=None, threshold=800, max_song_len=(44100*60)):
    all_gaps = filter(lambda x: x['mean'] < threshold, amps)
    gaps = []
    for i in xrange(len(all_gaps)):
        gap = all_gaps[i]
        if (len(gaps) == 0 or gaps[-1]['end'] + 44100 * 60 < gap['end']):
            gaps.append(gap)
    if verbose: pprint.pprint(gaps)
    if num is None:
        return gaps
    else:
        return sorted(sorted(gaps, key=lambda x: x['mean'])[0:num],
                      key=lambda x: x['start'])

def gap_shift(data, rate, gaps, shift=0.1, scale=1.5, pullback=0.5):
    results = []
    maxgap = max(gaps, key=lambda x: x['mean'])['mean'] * scale
    for gap in gaps:
        start = gap['end'] + rate * shift
        end = 0
        while end == 0 or next_vol < maxgap * scale:
            end = start + rate * shift
            next_vol = np.mean(abs(np.mean(data[start:end], 1)))
            start += rate * shift
        results.append(int(end - rate * (shift + pullback)))
    return results

def process_audio_file(data, rate, num_gaps=None):
    max_song_len = rate * 60
    amps = get_amplitudes(data, rate, 2, 1)
    gaps = find_gaps(amps, num=num_gaps, max_song_len=max_song_len)
    if (gaps[-1]['end'] + max_song_len > len(data)):
        gaps = gaps[0:len(gaps) - 1]
    track_pts = gap_shift(data, rate, gaps)
    print "Found %d songs." % (len(track_pts) + 1)
    if verbose: pprint.pprint(track_pts)
    return track_pts

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
            samples_to_string(start, rate), samples_to_string(end, rate))
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
    group.add_argument("-d", "--detect", action="store_true",
                       help="detect track starts and write to file")
    group.add_argument("-c", "--chop", type=str,
                       metavar="slice-file",
                       help="chop file using given track start file")
    parser.add_argument("-t", "--tracks", type=int, metavar="num-tracks",
                        help="number of tracks in input file")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="toggle more verbose output")
    args = parser.parse_args()

    verbose = args.verbose
    (rate, data) = sp.read(args.infile, mmap=True)
    if args.detect:
        starts = process_audio_file(data, rate, num_gaps=args.tracks)
        save_song_starts(args.outfile, rate, starts)
    elif args.chop is not None:
        starts = load_song_starts(args.chop, rate)
        chop_audio_file(data, rate, starts, args.outfile)
    else:
        starts = process_audio_file(data, rate, num_gaps=args.tracks)
        chop_audio_file(data, rate, starts, args.outfile)