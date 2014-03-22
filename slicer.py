import pprint
import sys
import os
import json
import argparse
import string

import numpy as np
import scipy.io.wavfile as sp

# TODO: Add a low-pass filter!

verbose = True

def samples_to_string(samples, rate, usems=False):
    """Convert a number of samples at a given rate to mm:ss(:ms)"""
    minutes = (samples / rate) / 60
    seconds = (samples / rate) % 60
    if (usems):
        ms = ((samples % rate) / (rate / 1000.))
        return "%d:%02d:%03d" % (minutes, seconds, ms)
    else:
        return "%d:%02d" % (minutes, seconds)
        
def string_to_samples(s, rate):
    """Convert a string of the form 'mm:ss(:ms)' to a quantity of samples"""
    items = s.split(":")
    minutes = int(items[0])
    seconds = int(items[1], base=10)
    if (len(items) == 3):
        ms = int(items[2])
        return ((minutes * rate * 60) + (seconds * rate)
                 + int(ms * (rate / 1000.)))
    else:
        return (minutes * rate * 60) + (seconds * rate)

def get_amplitudes(d, rate, samples_per_slice, shift_per_slice):
    """
    Given an audio file with a particular sample rate, a quantity of samples
    per slice, and an amount to shift every slice, returns an array of
    amplitude slices as dicts with keys 'start', 'end' and 'mean' (amplitude).
    
    Note that splitting samples_per_slice and shift_per_slice into two parts
    means you can have overlappying amplitude slices.
    """
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
    """
    Given a list of amplitude slices, and, optionally, a number of slices to 
    find, a low amplitude threshold, and a maximuim song length, returns a 
    num-length list of detected "gaps" (same format as amplitude slices) at
    least max_song_len apart whose mean amplitudes are below threshold.
    
    Returns all gaps below threshold if no num is specified.
    
    Note that the returned list is sorted based on the order that the gaps 
    appear in the file being sliced.
    """
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

def gap_shift(data, rate, gaps, shift=0.2, scale=1.6, pullback=0.1):
    """
    Given the song data, sampling rate, and a list of approximate detected 
    gaps that need to be moved forward (such that gaps are at the end of 
    tracks as opposed to the beginning), returns a list of corrected gaps 
    suitable for slicing.
    
    The algorithm takes a slice and compares it to the next slice, 
    attempting to detect increases in volume. The shift parameter controls 
    the size of these slices, the scale parameter controls the amplitude 
    threshold, and the pullback determines how far back to move the actual 
    slice once the next track's start has been found (it's good to have a 
    small gap at the beginning of tracks, and it helps prevent errors with 
    tracks that start gradually).
    """
    results = []
    maxgap = np.mean([x['mean'] for x in gaps]) * scale
    for i in xrange(len(gaps)):
        gap = gaps[i]
        start = gap['end'] + rate * shift
        end = 0
        while end == 0 or next_vol < maxgap:
            end = start + rate * shift
            next_vol = np.mean(abs(np.mean(data[start:end], 1)))
            start += rate * shift
        results.append(int(end - rate * (shift + pullback)))
    return results

def process_audio_file(data, rate, num_gaps=None):
    """
    Given an audio file at a sampling rate with an optionally specified 
    number of tracks, returns a list of track starts suitable for slicing.
    """
    max_song_len = rate * 90
    if verbose: print "Getting amplitudes..."
    amps = get_amplitudes(data, rate, 2, 1)
    if verbose: print "Done!"
    if verbose: print "Finding gaps..."
    gaps = find_gaps(amps, num=num_gaps, max_song_len=max_song_len)
    # If a gap is detected too close to the song end, remove it.
    if (gaps[-1]['end'] + max_song_len > len(data)):
        gaps = gaps[0:len(gaps) - 1]
    print "Found %d songs." % (len(gaps) + 1)
    if verbose: print "Shifting gaps..."
    track_pts = gap_shift(data, rate, gaps)
    if verbose: print "Done!"
    return track_pts

def chop_audio_file(data, rate, song_starts, save_dir):
    """
    Given an audio file at a sampling rate, a list of song starts, and a 
    save directory, slices the audio file at those points and outputs 
    numbered files in save_dir.
    
    Note that song_starts should just provide the "middle" track slice 
    points: beginning and end of the audio file are implicit within the 
    list. Thus, a file with n songs should have n-1 items in song_starts.
    """
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
    """
    Given a filename, a sample rate, and a list of song starts, outputs a 
    human-readable list of start locations in JSON format.
    """
    start_strings = [samples_to_string(st, rate, usems=True) for st in song_starts]
    f = open(filename, 'w')
    json.dump(start_strings, f)
    f.close()

def load_song_starts(filename, rate):
    """
    Given a filename containing a JSON format list of start locations and a 
    sample rate, returns the corresponding list of integer sample locations.
    """
    f = open(filename, 'r')
    start_strs = json.load(f)
    f.close();
    starts = [string_to_samples(s, rate) for s in start_strs]
    return starts

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="slice vinyl rips into individual tracks")
    parser.add_argument("infile", help="input audio file")
    parser.add_argument("-t", "--tracks", type=int, metavar="num-tracks",
                        help="number of tracks in input file")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-d", "--dump", action="store_true",
                       help="dump track starts to file (does not slice)")
    group.add_argument("-l", "--load-slices", action="store_true",
                       help="load slices from file instead of detecting them")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="toggle more verbose output")
    args = parser.parse_args()

    verbose = args.verbose
    dumpfile = string.replace(args.infile, ".wav", ".txt")
    outfolder = string.replace(args.infile, ".wav", "")
    (rate, data) = sp.read(args.infile, mmap=True)
    if args.dump is not None:
        starts = process_audio_file(data, rate, num_gaps=args.tracks)
        save_song_starts(dumpfile, rate, starts)
    else:
        if args.load_slices is not None:
            starts = load_song_starts(dumpfile, rate)
        else:
            starts = process_audio_file(data, rate, num_gaps=args.tracks)
        chop_audio_file(data, rate, starts, outfolder)