"""
game.py: file to run the program
overall handler for the output to user
@TODO: 
"""
from PoseEstimation import *
from ContourDetection import *
from voice import *
# from mqtt import *
import cv2
import time 
import numpy as np
import random
import os
import paho.mqtt.client as mqtt
import json
import boto3
from botocore.config import Config
from botocore.client import ClientError
import key

# OUTPUT = '.\output\\'
# if os.path.isdir(OUTPUT) == False:
#     os.makedir(OUTPUT)
region='us-east-1'
ROOM = 'ece180d-team1-room-'

test_points = [(304, 88), (304, 136), (272, 160), (272, 216), (504, 152), (328, 152), (328, 232), (336, 264), (480, 192), (280, 368), (288, 416), (496, 192), (320, 368), (320, 416), (420, 420)]

FONTCOLOR = (255,255,255)
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONTSIZE = 1

ACCESS_KEY = key.ACCESS_KEY
SECRET_KEY = key.SECRET_KEY
# mfile.write("Hello World!")
# mfile.close()

# MQTT connection string
connection_string = "ece180d/team1"

# 1 to see all the contours, 2 to see the points after contour detection, 3 for testing the pause button
DEBUG = 0

# KEY Definitions
ENTER_KEY = 13
ESC_KEY = 27
UP_KEY = 38
DOWN_KEY = 40
ZERO_KEY = 48
ONE_KEY = 49
BACK_KEY = 8

STATE_WAITING_FOR_CREATOR = 0
STATE_WAITING_FOR_POSE_RECEIPT = 1
STATE_GOT_POSE = 2
STATE_MY_TURN = 3




# WINDOW Definition 
WINDOWNAME = 'Hole in the Wall!'
cv2.namedWindow(WINDOWNAME, cv2.WND_PROP_FULLSCREEN)
cv2.setWindowProperty(WINDOWNAME,cv2.WND_PROP_FULLSCREEN,cv2.WINDOW_FULLSCREEN)

# FILESYSTEM Definitions 
GRAPHICS = '.\graphics\\'
POSES = 'poses\\'
POWERUPS = 'powerups\\'
PATH = GRAPHICS + POSES
DIFFICULTIES = ['easy\\', 'medium\\', 'hard\\']

# FILESYSTEM Work 
powerup_pictures = {}
powerup_dir = GRAPHICS + POWERUPS
power_up_file_names = os.listdir(powerup_dir)
for powerup_file_name in power_up_file_names:
    powerup = cv2.imread(powerup_dir + powerup_file_name)
    powerup_pictures[powerup_file_name] = powerup
    
easy_contours = []
medium_contours = []
hard_contours = []
for difficulty in DIFFICULTIES:
    cur_dir = PATH + difficulty
    for contour_file in os.listdir(cur_dir):
        img = cv2.imread(cur_dir + contour_file)
        img = cv2.bitwise_not(img)
        if difficulty == 'easy\\':
            easy_contours.append(img)
        if difficulty == 'medium\\':
            medium_contours.append(img)
        if difficulty == 'hard\\':
            hard_contours.append(img)
contour_pictures = []
contour_pictures.extend(easy_contours)
contour_pictures.extend(medium_contours)
contour_pictures.extend(hard_contours)
if DEBUG == 1:
    print(len(contour_pictures))
    for picture in easy_contours:
        cv2.imshow('test', picture)
        cv2.waitKey(0)


class Game():
    def __init__(self):
        # Capturing Video
        self.cap = cv2.VideoCapture(0)
        self.width  = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # OpenPose
        self.PoseEstimator = PoseEstimation() # openPose implementation object
        self.PoseDetector = ContourDetection() # pose detector algorithm created 
        
        # Voice
        self.command_dict = {   
            "activate" : self.activate,
            "slow down" : self.help
        }
        self.voice = commandRecognizer(self.command_dict)
        self.voice.listen()

        # MQTT
        self.client_mqtt = mqtt.Client()
        self.client_mqtt.on_connect = self.on_connect
        self.client_mqtt.on_disconnect = self.on_disconnect
        self.client_mqtt.on_message = self.on_message
        self.client_mqtt.connect_async('broker.hivemq.com') # 2. connect to a broker using one of the connect*() functions.
        self.client_mqtt.loop_start() # 3. call one of the loop*() functions to maintain network traffic flow with the broker.
        self.users = {}
        self.num_users = 0

        # powerups
        self.powerup_vals = {} 
        for powerup_file_name in power_up_file_names:
            self.powerup_vals[powerup_file_name] = 0
        # self.powerup_vals['speed up'] = 2
        # self.powerup_vals['slow down'] = 2
        self.speed_up_used = False
        self.slow_down_used = False
        
        #AWS 
        my_config = Config(
            region_name = region
        )

        self.client_aws = boto3.client(
            's3',
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY
        )
        self.room = ['*','*','*','*','*','*']
        self.password = []
        self.true_pass = ''
        self.nickname = []
        self.bucket = None
        self.creator = 0 # 1 for creator, 0 for joiner 
        self.room_name = '' 
        self.multi_start = 0 #should we start or no (creator tells the rest)

        # User variables
        self.user_score = 0
        self.level_number = 0
        self.uservid_weight = 1
        self.mode = -1 # 0 for single player, 1 for multi player
        self.difficulty = -1 # 0 for easy, 1 for medium, 2 for hard
        self.TIMER_THRESHOLD = 20
        self.play = False
        self.reset_timer = -1

        # multi user variables
        self.send_my_pose = 0 #1 means I'm the pose leader --> local user makes a pose
        self.move_on = 1 #1 means round is over, creator chooses next pose leader --> CREATOR only 
        self.pose_updated = 0 #1 means pose leader sent pose over mqtt --> ALL users should fit in hole 
        self.waiting_for_others = 0 #1 means that we (local user is pose leader) have sent our pose across and are waiting for others to finish fitting inside the hole 
        self.pose = [] # the pose we received from the pose leader 
        self.next_leader = 0 #1 means next leader has been chosen, move on to pose stuff
        # self.my_state
        self.pose_leader = ''
        self.round_scores = {} # creator keeps track of who has what scores 
    # start mqtt 
    def on_connect(self, client, userdata, flags, rc):
        print("Connection returned result: "+str(rc))
        
    def on_disconnect(self, client, userdata, rc):
        if rc != 0:
            print('Unexpected Disconnect')
        else:
            print('Expected Disconnect')

    def on_gesture(self,gesture):
        if gesture == 'wave':
            # add 1 to activate powerup count 
            if self.play == False:
                return
            if self.powerup_vals[power_up_file_names[0]] < 3:
                self.powerup_vals[power_up_file_names[0]] += 1
            else:
                pass # try to add more points for the level 
        elif gesture == 'tap':
            # add 1 to help powerup count 
            if self.play == False:
                return
            if self.powerup_vals[power_up_file_names[1]] < 3:
                self.powerup_vals[power_up_file_names[1]] += 1
            else:
                pass # try to add more points for the level 
        elif gesture == 'double_tap':
            # pause/un-pause
            if self.play:
                self.play = False
                self.reset_timer = time.perf_counter()
            else:
                self.play = True
                self.TIMER_THRESHOLD += int(time.perf_counter() - self.reset_timer)
                self.reset_timer = -1

    def on_message(self, client, userdata, message):
        print('Received message: "' + str(message.payload) + '" on topic "' +
        message.topic + '" with QoS ' + str(message.qos))
        packet = json.loads(message.payload)
        # print(packet["username"])
        user = packet["username"]

        if "leader" in packet:
            self.next_leader = 1
            self.pose_leader = packet["leader"]
            if packet["leader"] == ''.join(self.nickname): ## I am the leader 
                self.send_my_pose = 1
            else: ## ___ is the leader 
                self.pose_updated = 0 
                self.move_on = 0
                self.send_my_pose = 0 
        if "round_over" in packet: # creator sends this across when the round is over --> don't keep waiting for others now
            self.waiting_for_others = 0
            self.move_on = 1
        if "gesture" in packet:
            print(packet["gesture"])
            self.on_gesture(packet["gesture"])
        if "send_my_pose" in packet and user != ''.join(self.nickname):
            self.pose_updated = 1
            self.pose = packet["pose"]
            print(type(self.pose))
            print(packet["pose"])
            pass 
        if "score" in packet and self.creator == 1:
            # print(packet["score"])
            # indicate next round
            self.round_scores[packet["username"]] = packet["score"]
            if len(self.round_scores) == self.num_users:
                ## round is over 
                self.move_on = 1
                """
                implement csv logic here
                """
                packet = {
                    "username": ''.join(self.nickname),
                    "round_over": 1
                }
                self.client_mqtt.publish(self.room_name, json.dumps(packet), qos=1)
                self.round_scores = {}

        if "join" in packet and self.creator == 1: # assuming initial message sends score
            # implement some stuff creator has to do when new players join via mqtt 
            # print(packet["join"])
            if packet["join"] == True:
                # joining 
                # if self.num_users == 4:
                #     pass # don't let them join, implement later 
                f = open("room_info.csv", "a")
                f.write('{},{}\n'.format(user, 0))
                f.close()
                self.client_aws.upload_file('room_info.csv', self.room_name, "room_info.csv")
                self.num_users += 1
                self.users[self.num_users] = user
            pass 
        if "start_mult" in packet and self.creator == 0:
            self.multi_start = 1
        
    # end mqtt
    def createaws(self):
        valid = 0
        try:
            self.bucket = self.client_aws.create_bucket(Bucket= self.room_name)
            # print(self.bucket)
        except:
            self.show_screen('could_not_create')
            valid = 1
        if valid == 1:
            self.game()
        try:
            self.client_aws.head_object(Bucket=self.room_name, Key='room_info.csv')
        except ClientError as e:
            #print('does not exist') ## you're the creator 
            self.creator = 1 
            self.users[self.num_users] = ''.join(self.nickname)
            self.client_mqtt.subscribe(self.room_name, qos=1)
            packet = {
                "username": ''.join(self.nickname)
            }
            self.client_mqtt.publish(self.room_name, json.dumps(packet), qos=1)
            print(self.room_name)
            f = open("room_info.csv", "w")
            f.write('{},{}\n'.format(''.join(self.nickname),self.user_score))
            f.close()
            self.client_aws.upload_file('room_info.csv', self.room_name, "room_info.csv")
            #local file name, bucket, remote file name
            return

        # you're the joiner 
        self.client_mqtt.subscribe(self.room_name, qos=1)
        print(self.room_name)
        packet = {
            "username": ''.join(self.nickname),
            "join": True
        }
        self.client_mqtt.publish(self.room_name, json.dumps(packet), qos=1)

    
    def activate(self):
        if self.play == False:
            return
        print("activate command called")
        if self.powerup_vals[power_up_file_names[0]] > 0:
            self.powerup_vals[power_up_file_names[0]] -= 1
            self.speed_up_used = True

    def help(self):
        if self.play == False:
            return
        print("help command called")   
        if self.powerup_vals[power_up_file_names[1]] > 0:
            self.powerup_vals[power_up_file_names[1]] -= 1
            self.slow_down_used = True
    
    def show_screen(self, screen_type, points = 0):
        frame = np.zeros(shape=[self.height, self.width, 3], dtype=np.uint8)
        txt = ''
        if screen_type == 'start':
            words = ['HOLE ', 'IN ', 'THE ', 'WALL']
            for word in words:
                txt += word
                cv2.putText(frame, txt, (140, 220), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                cv2.imshow(WINDOWNAME, frame)
                while True:
                    if cv2.waitKey(500): 
                        break
            cv2.putText(frame, "Single Player Mode --- Enter", (175, 300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "Multi-Player Mode --- 1", (175, 350), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "-->",(135,300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            
            while True:
                key = cv2.waitKey(0)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                elif key == ENTER_KEY:
                    if self.mode == -1:
                        self.mode = 0
                    break
                elif key == ONE_KEY:
                    if self.mode != -1 and self.mode != 0:
                        continue
                    self.mode = 1
                    frame = np.zeros(shape=[self.height, self.width, 3], dtype=np.uint8)
                    cv2.putText(frame, txt, (140, 220), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Single Player Mode --- 0", (175, 300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Multi-Player Mode --- Enter", (175, 350), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "-->",(135,350), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.imshow(WINDOWNAME, frame)
                elif key == ZERO_KEY:
                    if self.mode == 0:
                        continue
                    self.mode = 0
                    frame = np.zeros(shape=[self.height, self.width, 3], dtype=np.uint8)
                    cv2.putText(frame, txt, (140, 220), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Single Player Mode --- Enter", (175, 300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Multi-Player Mode --- 1", (175, 350), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "-->",(135,300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.imshow(WINDOWNAME, frame)
        elif screen_type == 'difficulty':
            cv2.putText(frame, 'Select a difficulty:', (140, 220), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "-->",(135,300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "Easy --- Enter", (175, 300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "Medium --- \'m\'", (175, 350), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "Hard --- \'h\'", (175, 400), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            self.difficulty = 0
            while True:
                key = cv2.waitKey(0)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                elif key == ENTER_KEY:
                    break
                elif key == ord('e'):
                    frame = np.zeros(shape=[self.height, self.width, 3], dtype=np.uint8)
                    cv2.putText(frame, 'Select a difficulty:', (140, 220), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    self.difficulty = 0
                    cv2.putText(frame, "-->",(135,300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Easy --- Enter", (175, 300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Medium --- \'m\'", (175, 350), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Hard --- \'h\'", (175, 400), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.imshow(WINDOWNAME, frame)
                elif key == ord('m'):
                    frame = np.zeros(shape=[self.height, self.width, 3], dtype=np.uint8)
                    cv2.putText(frame, 'Select a difficulty:', (140, 220), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    self.difficulty = 1
                    cv2.putText(frame, "-->",(135,350), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Easy --- \'e\'", (175, 300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Medium --- Enter", (175, 350), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Hard --- \'h\'", (175, 400), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.imshow(WINDOWNAME, frame)
                elif key == ord('h'):
                    frame = np.zeros(shape=[self.height, self.width, 3], dtype=np.uint8)
                    cv2.putText(frame, 'Select a difficulty:', (140, 220), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    self.difficulty = 2
                    cv2.putText(frame, "-->",(135,400), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Easy --- \'e\'", (175, 300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Medium --- \'m\'", (175, 350), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.putText(frame, "Hard --- Enter", (175, 400), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.imshow(WINDOWNAME, frame)       
        elif screen_type == 'level':
            words = ['LEVEL ', '{}'.format(self.level_number)]        
            for word in words:
                txt += word
                cv2.putText(frame, txt, (140, 220), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                cv2.imshow(WINDOWNAME, frame)
                while True:
                    if cv2.waitKey(500): 
                        break
            cv2.putText(frame, "Press any key to start.", (140, 300), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            while True:
                key = cv2.waitKey(0)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                elif key > 0: 
                    break
        elif screen_type == 'level_end':
            words = ['Level End']
            for word in words:
                txt += word
                cv2.putText(frame, txt, (140, 220), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                cv2.imshow(WINDOWNAME, frame)
                while True:
                    if cv2.waitKey(500): 
                        break
            if self.speed_up_used:
                cv2.putText(frame, "DOUBLE POINTS!!", (140, 300), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "This round: {} points".format(points), (140, 350), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "Overall: {} points".format(self.user_score), (140, 400), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            while True:
                key = cv2.waitKey(4000)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                break
        elif screen_type == 'pause':
            cv2.putText(frame, 'Pause Screen', (140, 220), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "Main Menu --- Enter", (175, 300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "Exit --- ESC Key", (175, 350), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "Un-pause ---- Double Tap Gesture", (175, 400), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "-->",(135,300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            if DEBUG == 3:
                return cv2.waitKey(0)
        elif screen_type == 'room':
            cv2.putText(frame, "Enter a room code:",(115,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            for i in range(len(self.room)):
                cv2.putText(frame, self.room[i], (115+ 20*i,300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            num = 0

            while True:
                key = cv2.waitKey(0)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                elif num >= len(self.room) and key == ENTER_KEY:
                    return # go to aws creation
                else:
                    if num >= len(self.room):
                        continue
                    if key == BACK_KEY:
                        self.room[num] = '*'
                        if num > 0:
                            num -= 1
                    elif chr(key)!= '*':
                        self.room[num] = chr(key)
                        num += 1
                    frame = np.zeros(shape=[self.height, self.width, 3], dtype=np.uint8)
                    cv2.putText(frame, "Enter a room code:",(115,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    for i in range(len(self.room)):
                        cv2.putText(frame, self.room[i], (115+ 20*i,300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.imshow(WINDOWNAME, frame)
        elif screen_type == 'nickname':
            cv2.putText(frame, "Nickname:",(115,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            while True:
                key = cv2.waitKey(0)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                elif key == ENTER_KEY:
                    self.nickname = ''.join(self.nickname)
                    return 
                else:
                    if key == BACK_KEY:
                        if len(self.nickname) > 0:
                            self.nickname.pop()
                    else: 
                        self.nickname.append(chr(key))
                    frame = np.zeros(shape=[self.height, self.width, 3], dtype=np.uint8)
                    cv2.putText(frame, "Nickname:",(115,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    for i in range(len(self.nickname)):
                        cv2.putText(frame, self.nickname[i], (115+ 20*i,300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.imshow(WINDOWNAME, frame)
            return
        elif screen_type == 'no_room':
            cv2.putText(frame, "Room {}".format(ROOM+''.join(self.room)),(140,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.putText(frame, "does not exist. Please try again later.",(140,240), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            while True:
                key = cv2.waitKey(0)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                elif key == ENTER_KEY:
                    self.multiplayer()
        elif screen_type == 'could_not_create':
            cv2.putText(frame, "Could not create room. Please try again.".format(ROOM+''.join(self.room)),(140,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            while True:
                key = cv2.waitKey(0)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                elif key == ENTER_KEY:
                    self.multiplayer()
        elif screen_type == 'password':
            cv2.putText(frame, "Enter the room password:",(140,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            for i in range(len(self.room)):
                cv2.putText(frame, self.room[i], (130+ 20*i,300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            num = 0
            while True:
                key = cv2.waitKey(0)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
          
                elif ''.join(self.password) == self.true_pass and key == ENTER_KEY:
                    return # password is correct
                else:
                    if key == BACK_KEY:
                        if len(self.password) > 0:
                            self.password.pop()
                    else: 
                        self.nickname.append(chr(key))    
                    frame = np.zeros(shape=[self.height, self.width, 3], dtype=np.uint8)
                    cv2.putText(frame, "Enter the room password:",(140,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    for i in range(len(self.password)):
                        cv2.putText(frame, '*', (115+ 20*i,300), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
                    cv2.imshow(WINDOWNAME, frame)
            return
        elif screen_type == 'start_game_multi':
            cv2.putText(frame, "Press Enter to Start the Game".format(ROOM+''.join(self.room)),(140,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            while True:
                key = cv2.waitKey(0)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                elif key == ENTER_KEY:
                    # send an update to everybody 
                    # game start 
                    packet = {
                        "username": ''.join(self.nickname),
                        "start_mult": True
                    }
                    self.client_mqtt.publish(self.room_name, json.dumps(packet), qos=1)
                    return
        elif screen_type == 'waiting_for_creator':
            cv2.putText(frame, "Please wait for creator to start the game".format(ROOM+''.join(self.room)),(140,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            while True:
                key = cv2.waitKey(10)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                if self.multi_start == 1:
                    return
                pass
        elif screen_type == 'waiting_for_new_pose':
            cv2.putText(frame, "Please wait, assigning new leader.",(140,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            start_time = time.perf_counter()
            while True: #while in this loop, we're waiting for pose leader 
                key = cv2.waitKey(10)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                time_elapsed = int(time.perf_counter() - start_time)
                time_remaining = 2 - time_elapsed
                cv2.imshow(WINDOWNAME, frame)
                if time_remaining <= 0: 
                    break
                
            frame = np.zeros(shape=[self.height, self.width, 3], dtype=np.uint8)
            txt = ''
            cv2.putText(frame, "Please wait for user {} to create a pose".format(self.pose_leader),(140,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            while True: #while in this loop, we're waiting for pose leader 
                key = cv2.waitKey(10)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                if self.pose_updated == 1: #local user tries to fit in the hole now
                    start_time = time.perf_counter()
                    while True:
                        key = cv2.waitKey(1)
                        _, frame = self.cap.read()
                        time_elapsed = int(time.perf_counter() - start_time)
                        time_remaining = 5 - time_elapsed
                        contour_weight = 1
                        contour, _ = self.PoseEstimator.getContourFromPoints(self.pose)
                        contour = cv2.bitwise_not(contour)
                        frame = cv2.addWeighted(frame,self.uservid_weight,contour,contour_weight,0)
                        cv2.imshow(WINDOWNAME, frame)
                        if time_remaining <= 0: 
                            cv2.imshow(WINDOWNAME, frame)
                            frame, points = self.PoseEstimator.getPoints(frame)
                            level_score = self.PoseDetector.isWithinContour(points, contour)
                            packet = {
                                "username": ''.join(self.nickname),
                                "score": level_score
                            }
                            self.client_mqtt.publish(self.room_name, json.dumps(packet), qos=1)
                            self.pose_updated = 0
                            break
                    return
                if self.send_my_pose == 1:
                    self.send_pose()
                    self.waiting_for_others = 1
                    self.show_screen('waiting_for_others_pose')
                    return
                if self.move_on == 1 and self.creator == 1:
                    return
                pass    
        elif screen_type == 'level_end_multi':
            cv2.putText(frame,'Your score is {}'.format(5), (140, 220), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            while True:
                key = cv2.waitKey(10)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                if self.next_leader == 1:
                    self.next_leader = 0
                    return
                if self.move_on == 1 and self.creator == 1:
                    return
        elif screen_type == 'waiting_for_others_pose':
            cv2.putText(frame, "Waiting for other users to match your pose",(140,220), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            cv2.imshow(WINDOWNAME, frame)
            while True: #while in this loop, we're waiting for pose leader 
                key = cv2.waitKey(10)
                if key == ESC_KEY:
                    self.__del__()
                    exit(0)
                if self.waiting_for_others == 0: #we're no longer waiting --> signify end of turn
                    return
                pass    
    def editFrame(self, frame, start_time, contour, override_time = False):
        original = np.copy(frame)
        time_elapsed = int(time.perf_counter()-start_time)
        time_remaining = self.TIMER_THRESHOLD - time_elapsed
        if time_remaining <= 0 or override_time == True:
            time_remaining = 0

        if time_elapsed < self.TIMER_THRESHOLD*.2: #80% --> want no opacity
            contour_weight = 0
        elif time_elapsed > self.TIMER_THRESHOLD*.8: #20% --> want full opacity
            contour_weight = 1
        else:
            contour_weight = 5.0/(3.0*self.TIMER_THRESHOLD)*(time_elapsed-0.2*self.TIMER_THRESHOLD)+1.0/3.0 # grab a weight based on the time that's elapsed 

        frame = cv2.addWeighted(frame,self.uservid_weight,contour,contour_weight,0)
        num = 1
        
        for powerup_file_name in power_up_file_names:
            powerup = powerup_pictures[powerup_file_name]
            powerup_num_left = self.powerup_vals[powerup_file_name]
            row_bias = num*60 + 40
            col_bias = 20
            rows1,cols1,channels1 = powerup.shape
            rows2,cols2,channels2 = frame.shape
            # print(rows2-rows1- row_bias, rows2-row_bias)
            # print((cols2-cols1-col_bias),(cols2-col_bias))
            row_1 = rows2 - rows1 - row_bias
            row_2 = rows2 - row_bias
            col_1 = cols2 - cols1 - col_bias
            col_2 = cols2 - col_bias
            roi = frame[(row_1):(row_2), (col_1):(col_2) ]
            powerupgray = cv2.cvtColor(powerup,cv2.COLOR_BGR2GRAY)
            ret, mask = cv2.threshold(powerupgray, 10, 255, cv2.THRESH_BINARY)
            mask_inv = cv2.bitwise_not(mask)
            frame_bg = cv2.bitwise_and(roi,roi,mask = mask_inv)
            powerup_fg = cv2.bitwise_and(powerup,powerup,mask = mask)
            dst = cv2.add(frame_bg,powerup_fg)
            frame[(row_1):(row_2), (col_1):(col_2) ] = dst
            cv2.putText(frame, '{} x'.format(powerup_num_left), (640-110, 480-row_bias-20), FONT, .5, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
            num+=1
        
        cv2.putText(frame, "Time Remaining: {}".format(time_remaining), (10, 50), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
        cv2.putText(frame, "Score: {}".format(self.user_score), (500, 50), FONT, .8, FONTCOLOR, FONTSIZE, lineType=cv2.LINE_AA)
        # print('time remaining', time_remaining)
        return frame, time_remaining, original
    
    def level(self):
        self.play = True
        timer_old = self.TIMER_THRESHOLD
        
        if self.difficulty == 0:
            contour_num = random.randint(0,len(easy_contours)-1)
            contour = easy_contours[contour_num]
        elif self.difficulty == 1:
            contour_num = random.randint(0,len(medium_contours)-1)
            contour = medium_contours[contour_num]
        if self.difficulty == 2:
            contour_num = random.randint(0,len(hard_contours)-1)
            contour = hard_contours[contour_num]
        frame = np.zeros(shape=[self.height, self.width, 3], dtype=np.uint8)
        self.show_screen('level')
        start_time = time.perf_counter()
        # print(start_time)
        override_time=False
        stop = False
        while True:
            key = cv2.waitKey(1)
            if key == ESC_KEY:
                self.__del__()
                exit(0)
            elif key == ord('s') or self.speed_up_used == True:
                override_time = True
            if self.play == False:
                if key == ENTER_KEY:
                    self.game()
                self.show_screen('pause')
                pass
                continue
            if DEBUG == 3:
                if key == ord('p'):
                    if self.play:
                        self.play = False
                        self.reset_timer = time.perf_counter()
                        pass
                    while self.play == False:
                        new_key = self.show_screen('pause')
                        if new_key == ord('p'):
                            self.TIMER_THRESHOLD += int(time.perf_counter() - self.reset_timer)
                            self.reset_timer = -1
                            self.play = True
                        elif new_key == ESC_KEY:
                            self.__del__()
                            exit(0)
                        elif new_key == ENTER_KEY:
                            self.game()
                        
            else: # use only gesture code 
                pass
            if self.slow_down_used == True:
                self.TIMER_THRESHOLD *= 2
                self.slow_down_used = False
            
              
            _, frame = self.cap.read()
            frame, time_remaining, original = self.editFrame(frame, start_time, contour, override_time=override_time)
            cv2.imshow(WINDOWNAME, frame)
            if override_time == True and stop == False:
                start_time+=1
                stop = True
                continue
            if time_remaining <= 0: 
                self.TIMER_THRESHOLD = timer_old
                frame, time_remaining, original = self.editFrame(frame, start_time, contour, override_time=override_time)
                cv2.imshow(WINDOWNAME, frame)
                while True:
                    if cv2.waitKey(100):
                        break
                # print('original shape', original.shape)
                # print(contour.shape)
                frame, points = self.PoseEstimator.getPoints(original)
                level_score = self.PoseDetector.isWithinContour(points, contour)
                if DEBUG == 2:
                    cv2.imshow(WINDOWNAME, original)
                    while True:
                        if cv2.waitKey(0):
                            break
                if self.speed_up_used:
                    level_score *= 2
                self.user_score += level_score
                self.show_screen('level_end',points=level_score)
                return
            pass

    def singleplayer(self):
        while self.difficulty == -1:
            self.show_screen('difficulty')
        while True:
            self.level_number += 1
            self.slow_down_used = False
            self.speed_up_used = False
            self.play = False
            self.level()
            if self.TIMER_THRESHOLD > 5:
                self.TIMER_THRESHOLD -= 2
    def send_pose(self):
        ## include screen to say "you're up"
        self.move_on = 0
        start_time = time.perf_counter()
        while self.send_my_pose == 1: 
            key = cv2.waitKey(1)
            _, frame = self.cap.read()
            # frame, time_remaining, original = self.editFrame(frame, start_time, contour, override_time=override_time)
            cv2.imshow(WINDOWNAME, frame)
            time_elapsed = int(time.perf_counter() - start_time)
            time_remaining = 5 - time_elapsed
            if time_remaining <= 0: 
                cv2.imshow(WINDOWNAME, frame)
                self.send_my_pose = 0
                packet = {
                    "username": ''.join(self.nickname),
                    "send_my_pose": 1,
                    "pose": test_points
                }
                self.client_mqtt.publish(self.room_name, json.dumps(packet), qos=1)
                return
        pass 
    def creator_code(self):
        self.show_screen('start_game_multi') 
        # time.sleep(3)
        cur_user = 0
        while True:
            ## send message to person whose turn it is 
            if self.move_on == 0: #and self.users[cur_user] != ''.join(self.nickname):
                self.show_screen('waiting_for_new_pose')
                self.show_screen('level_end_multi')
            
            elif self.move_on == 1:
                if self.users[cur_user] == ''.join(self.nickname):
                    print('it\'s {}\'s turn'.format(self.users[cur_user]))
                    packet = {
                        "username": ''.join(self.nickname),
                        "leader": self.users[cur_user]
                    }
                    self.client_mqtt.publish(self.room_name, json.dumps(packet), qos=1)
                    self.send_my_pose = 1
                    self.send_pose()
                    self.waiting_for_others = 1
                    self.show_screen('waiting_for_others_pose')
                else:
                    packet = {
                        "username": ''.join(self.nickname),
                        "leader": self.users[cur_user]
                    }
                    print('it\'s {}\'s turn'.format(self.users[cur_user]))
                    self.client_mqtt.publish(self.room_name, json.dumps(packet), qos=1)
                    self.move_on = 0
            
                cur_user += 1
                cur_user %= (self.num_users+1)
    def joiner_code(self):
        self.show_screen('waiting_for_creator')
        while True:
            self.show_screen('waiting_for_new_pose')
            self.show_screen('level_end_multi')
            # we got a new pose 
            # for i in range(len(self.pose)):
            #     self.pose[i] = tuple(self.pose[i])
            # _, _ = self.PoseEstimator.getContourFromPoints(self.pose)
            # contour = cv2.imread('Output-Contour.jpg')
            # contour = cv2.bitwise_not(contour)
            # while True:
            #     key = cv2.waitKey(1)
            #     _, frame = self.cap.read()
            #     # frame = cv2.addWeighted(frame,self.uservid_weight,contour,1,0)
            #     cv2.imshow(WINDOWNAME, frame)
            
    def multiplayer(self):
        self.show_screen('room')
        self.show_screen('nickname') 
        self.room_name = ROOM + ''.join(self.room)
        print(self.room_name)
        self.createaws()
        if self.creator == 1:
            self.creator_code()
        else: # regular user 
            self.joiner_code()

    def game(self):
        self.user_score = 0
        self.level_number = 0
        self.uservid_weight = 1
        self.mode = -1 # 0 for single player, 1 for multi player
        self.difficulty = -1 # 0 for easy, 1 for medium, 2 for hard
        self.TIMER_THRESHOLD = 20
        self.play = False
        self.reset_timer = -1
        self.show_screen('start')
        self.nickname = []
        self.password = []
        # self.createorjoin = 0
        self.room = ['*','*','*','*','*','*']
        if self.mode == 0:
            self.singleplayer()
        elif self.mode == 1: 
            self.multiplayer()
        else:
            print('error')
            exit(1)

    def test(self):
        # frame = np.zeros(shape=[self.height, self.width, 3], dtype=np.uint8)
        # example_arr = [None, (352, 296), (320, 296), None, None, (416, 160), (296, 112), (256, 120), (352, 120), None, None, (488, 168), None, None, (440, 160)]
        # output = contour_pictures[0]
        # count = 0 
        # for point in example_arr:
        #     if point == None or point[0] > 480 or point[1] > 640:
        #         continue
        #         # cv2.circle(output, (point[0],point[1]), 8, (0, 255, 255), thickness=-1, lineType=cv2.FILLED)
        #     if output[point[0],point[1],0] > 20 and output[point[0],point[1],1] > 20 and output[point[0],point[1],2] > 20:
        #         count +=1
        # for point in example_arr:
        #     if point != None:
        #         cv2.circle(output, (point[0],point[1]), 8, (0, 255, 255), thickness=-1, lineType=cv2.FILLED)
        # print(count)
        # cv2.imshow('test',output)
        # while True:
        #     if cv2.waitKey(0):
        #         break
        # 
        # 
        # 
        # 
        
        
        
        
        # contour = cv2.imread('Output-Contour.jpg')
        # contour = cv2.bitwise_not(contour)
        # print(contour.shape)
        # while True: 
        #     _, frame = self.cap.read()
        #     # print(frame.shape)
        #     # frame = cv2.addWeighted(frame,self.uservid_weight,contour,1,0)
        #     cv2.imshow(WINDOWNAME, frame)
        pass 
    def __del__(self):
        cv2.destroyAllWindows()
        self.client_mqtt.loop_stop()
        self.client_mqtt.disconnect()
        self.voice.stop()
    

def main():
    game = Game()
    game.game()

if __name__ == '__main__':
    main()
