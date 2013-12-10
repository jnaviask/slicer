import pprint
import sys
import os
import json
import argparse

import numpy as np
import scipy.io.wavfile as sp

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

def find_track_gaps(d, rate, num_gaps=None):
    min_song_len = rate * 60
    gaps = []
    small_delta_scale = 2
    large_delta_scale = 1. / 2
    small_amp_scale = 800
    # This messy piece of crap filter the thing.
    time_per_gap = d[0]['end_sample'] - d[0]['start_sample']
    gaps_to_remove = min_song_len / time_per_gap
    dr = d[gaps_to_remove:len(d) - gaps_to_remove]
    dr_low_amp = [dr[i] for i in xrange(len(dr) - 1) if (dr[i]['start_val'] + dr[i]['end_val'] / 2) < small_amp_scale or (dr[i-1]['start_val'] + dr[i-1]['end_val']) / 2 < small_amp_scale]
    max_delta = max(dr_low_amp, key=lambda x: x['delta'])['delta']
    min_delta = abs(min(dr_low_amp, key=lambda x: abs(x['delta']))['delta'])
    #print max_delta, min_delta
    for i in xrange(len(dr_low_amp) - 1):
        gap = dr_low_amp[i]
        chg = dr_low_amp[i+1]
        # goal: gap has small delta, chg has large delta
        #     gap has small amplitude, chg has large amplitude
        score = abs(gap['delta']) / min_delta + max_delta / chg['delta']
        gaps.append({'gap': gap, 'chg': chg, 'score': score})
    results = []
    if (num_gaps is None):
        # make arbitrary bounds
        large_delta = 300
        small_delta = 300
        small_amp = 800
        for i in gaps:
            if (abs(i['gap']['delta']) < small_delta and
                    i['chg']['delta'] > large_delta and
                    (gap['start_val'] + gap['end_val'] / 2) < small_amp and
                    (len(results) == 0 or
                        (results[-1]['end_sample'] + min_song_len
                            < i['gap']['start_sample']))):
                results.append(i['gap'])
        return results
    else:
        sorted_gaps = sorted(gaps, key=lambda x: x['score'], reverse=True)
        idx = 0
        while (len(results) < num_gaps - 1):
            item = sorted_gaps[idx]['gap']
            far_enough = [(abs(item['end_sample'] - x['end_sample'])
                           > min_song_len) for x in results]
            if (all(far_enough)):
                #print "Found gap at idx", idx
                results.append(item)
            idx += 1
        return sorted(results, key=lambda x: x['start_sample'])
    
def process_audio_file(data, rate, num_gaps=None):
    amps = get_amplitudes(data, rate, 1, 0.5)
    deltas = get_deltas(amps)
    track_pts = find_track_gaps(deltas, rate, num_gaps=num_gaps)
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
    group.add_argument("-d", "--detect",
                       help="detect track starts and write to file",
                       action="store_true")
    group.add_argument("-c", "--chop", type=str,
                       metavar="slice-file",
                       help="chop file using given track start file")
    parser.add_argument("-t", "--tracks", type=int, metavar="num-tracks",
                        help="number of tracks in input file")
    args = parser.parse_args()

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