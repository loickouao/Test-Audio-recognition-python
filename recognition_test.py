import subprocess
import numpy as np

second = "5"
#bash_cmd = "python recognize-from-microphone.py -s "+second
bash_cmd = "python recognize-from-microphone.py"
process = subprocess.Popen(bash_cmd.split(), stdout=subprocess.PIPE)
output, err = process.communicate()
print(output)


AudioTrack = ["Documentaire","Discussion", "Motosportmag", "Football", "Music"]
BruitTrack = ["Whitenoise", "Conversation", "Football", "Enfants", "none"]
AudioBaselvl = [0, 25, 50, 75, 100]
BruitLvl = [0, 25, 50, 75, 100]

ListeningTime = [2, 5, 7, 10, 15]


