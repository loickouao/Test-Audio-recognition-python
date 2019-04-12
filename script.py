import pandas as pd
import itertools
import json
import subprocess
import re
from pydub import AudioSegment
from pydub.playback import play
import random
from libs.db_sqlite import SqliteDatabase
from recognize_from_microphone import listen
from get_database_stat import getsong
import time
from termcolor import colored
import os

import ray

ray.init()

@ray.remote
def playaudio(audiosample):
    play(audiosample)

@ray.remote
def listenaudio(time):
    result = listen(time)
    msg = '** ** result ** ** id audio: %d'
    print (colored(msg, 'yellow') % result)
    return result

def get_speaker_output_volume():
    """
    Get the current speaker output volume from 0 to 100.
    Note that the speakers can have a non-zero volume but be muted, in which
    case we return 0 for simplicity.
    Note: Only runs on macOS.
    """
    cmd = "osascript -e 'get volume settings'"
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    output, error = process.communicate()
    if error is None :
        pattern = re.compile(r"output volume:(\d+), input volume:(\d+), "
                            r"alert volume:(\d+), output muted:(true|false)")
        volume, _, _, muted = pattern.match(output).groups()

        volume = int(volume)
        muted = (muted == 'true')

    return 0 if muted else volume

def set_speaker_output_volume(audiolv):
    cmd = "osascript -e 'set Volume "+str(audiolv)+"'"
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    process.communicate()

"""
    For get the same average amplitude for a group of audio file
    basically you choose an average amplitude in dBFS
"""
def match_target_amplitude(sound, target_dBFS):
    change_in_dBFS = target_dBFS - sound.dBFS
    return sound.apply_gain(change_in_dBFS)

"""
get id of audio 
"""
def get_id_song(name_audio):
    db = SqliteDatabase()
    listsong = getsong(db)
    for song in listsong:
        print(song[1])

def run_test_with_config(testconfig):
    assert testconfig["Audiofile"] is not None, "Attention, you idiot have not specified an audiotrack"
    successful = 0  # number of good recognitions

    audio = AudioSegment.from_mp3(testconfig["Audiofile"])

    # pydub does things in miliseconds
    # audioLength = len(audio)

    # random selection of the beginning of the music
    # starttime = random.randint(1, audioLength - (testconfig["playback_time"] * 1000))

    starttime = testconfig["starttime"] * 1000

    # playback time of audio
    audiosample = audio[starttime:starttime + (testconfig["playback_time"] * 1000)]

    # same average amplitude
    audiosample = match_target_amplitude(audiosample, -20.0)
    audiosample = audiosample - testconfig["AudioLevel"]

    # Returns the loudness of the AudioSegment in dBFS (db relative to the maximum possible loudness)
    # audioLoudness = audiosample.dBFS

    # vol = get_speaker_output_volume()
    # print (colored('** volume ** : '+str(vol)+"%", 'green'))
    audiolv = (testconfig["OuputLevel"] * 16 ) / 100
    set_speaker_output_volume(audiolv)

    if testconfig["Distractions"] == "None":
        return_id1 = playaudio.remote(audiosample)
    else:
        distraction = AudioSegment.from_mp3(testconfig["Distractions"])
        #distractionength = len(distraction)
        
        #startdist = random.randint(1, distractionength - testconfig["playback_time"] * 1000)
        startdist = testconfig["starttime"] * 1000
        # playback time of distraction
        distractionsample = distraction[startdist:startdist + (testconfig["playback_time"] * 1000)]

        # same average amplitude
        distractionsample = match_target_amplitude(distractionsample, -20.0)

        return_id1 = playaudio.remote(audiosample)

        distractionsample = distractionsample - testconfig["NoiseLevel"]
        return_id3 = playaudio.remote(distractionsample)

    
    if testconfig["playback_time"] > testconfig["TimeListening"]:
        time.sleep(1)
   
    return_id2 = listenaudio.remote(testconfig["TimeListening"])

    # Python object from the corresponding remote object, the command wait until all the remote object has been created   
    try:
        ret1, ret2, ret3 = ray.get([return_id1, return_id2, return_id3]) 
    except NameError:
        ret1, ret2 = ray.get([return_id1, return_id2])         

    name_audio = testconfig["Audiofile"].split("/")
    name_audio = name_audio[len(name_audio)-1]
    get_id_song(name_audio)

    if (ret2 != 0):
        successful = 1
    return successful

def run_test(idx, config):
    default_config = {
        'Repetitions': 1,
        'starttime' : 1,
        'Audiofile': None,
        'AudioLevel': 100,
        'TimeListening': 5,
        'playback_time': 5,
        'NoiseLevel': 50,
        'Distractions': None,
        "OuputLevel": 0

    }
    testconfig = default_config.copy()
    testconfig.update(config)
    # reps = testconfig["Repetitions"]
    # playback_time = testconfig["playback_time"]
    # print(f"This will take about {reps * (playback_time + 5)} seconds")
    print("playback_time:", testconfig["playback_time"], "TimeListening:", testconfig["TimeListening"], "distraction:", testconfig["Distractions"], "AudioLevel", testconfig["AudioLevel"], "NoiseLevel", testconfig["NoiseLevel"], "OuputLevel", testconfig["OuputLevel"], "starttime", testconfig["starttime"])
    
    totalsuccess = 0
    rep = 0
    while rep < testconfig["Repetitions"]:
        successful = run_test_with_config(testconfig)
        totalsuccess = totalsuccess + successful
        rep = rep + 1
    testconfig["successful"] = totalsuccess
    return testconfig


def main():

    #normalize_with_ffmpeg()

    with open("./configtest/config.json") as filehandle:
        config = json.load(filehandle)
    
    dimensions = []
    for key, values in config.items():
        key_value_pairs = [ (key, value) for value in values]
        dimensions.append(key_value_pairs)

    idx = 0

    results = []

    for configs in itertools.product(*dimensions):
        idx += 1
        # wait a few seconds before performing the next test for the time of the prints result
        time.sleep(1)
        print(idx)
        #print("Running test",idx,"of",total_tests)
        result = run_test(idx, dict(configs))
        results.append(result)
        if idx % 5 == 0 :
            if ray.is_initialized():
                ray.shutdown()
            if not ray.is_initialized():
                ray.init()
            
            df = pd.DataFrame(results) 
            results = []
            if os.path.isfile('result.csv'):
                df.to_csv("result.csv", sep='\t', encoding='utf-8', index = False, header = False, mode='a')  
            else:
                df.to_csv("result.csv", sep='\t', encoding='utf-8', index = False, header = True, mode='a')             

    #df = pd.DataFrame(results) 
    # nice code for results -> csv / Pandas
    # print(df.to_csv("result.csv", sep='\t', encoding='utf-8'))

if __name__ == "__main__":
    # execute only if run as a script
    
    main()

 

