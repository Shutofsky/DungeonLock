#!/usr/bin/python
import RPi.GPIO as GPIO
import serial
import time
from datetime import datetime
from datetime import timedelta
import string
import sqlite3
import pygame
import paho.mqtt.client as mqtt
import socket

start_time = datetime.now()

def millis():
    dt = datetime.now() - start_time
    ms = (dt.days * 24 * 60 * 60 + dt.seconds) * 1000 + dt.microseconds / 1000.0
    return ms

def on_connect(client, userdata, flags, rc):
    client.subscribe("LOCK/#")

def on_message(client, userdata, msg):
    global my_ip
    global soundFlag
    global dbName
    global Cur_Lock_State
    commList = str(msg.payload).split('/')
    if commList[0] != my_ip and commList[0] != '*':
        return()
    if commList[1] == 'PING':
        client.publish("LOCKASK", my_ip + '/PONG')
    elif commList[1] == 'OPEN':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("UPDATE current_state SET Lock_Status = 'open' WHERE id=1")
        conn.commit()
        conn.close()
    elif commList[1] == 'CLOSE':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("UPDATE current_state SET Lock_Status = 'closed' WHERE id=1")
        conn.commit()
        conn.close()
    elif commList[1] == 'NOSOUND':
        soundFlag = 0
        pygame.mixer.music.stop()
    elif commList[1] == 'SOUND':
        soundFlag = 1
        if Cur_Lock_State == 'closed':
            pygame.mixer.music.play(loops=-1)
    elif commList[1] == 'STATUS':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        S = commList[2].lower()
        print S
        req.execute("UPDATE current_state SET Base_Status = ? WHERE id=1",[S])
        conn.commit()
        conn.close()

def Open_Door():
    global soundFlag
    global dbName
    global my_ip
    global doorCheckTime
    global doorTime
    global Cur_Lock_State
    if soundFlag == 1:
        pygame.mixer.music.stop()
        pygame.mixer.music.load("/home/pi/Zamknulo.mp3")
        pygame.mixer.music.play()
    Cur_Lock_State="open"
    client.publish("LOCKASK",my_ip + "/OPENED")
    conn = sqlite3.connect(dbName)
    req = conn.cursor()
    req.execute("UPDATE current_state SET Lock_Status = ? WHERE id=1",[Cur_Lock_State])
    conn.commit()
    conn.close()
    GPIO.output(4,False)
    doorTime = millis()

def Close_Door():
    global soundFlag
    global dbName
    global my_ip
    global doorCheckTime
    global doorTime
    global Cur_Lock_State
    if soundFlag == 1:
        pygame.mixer.music.load("/home/pi/Zamknulo.mp3")
        pygame.mixer.music.play()
        while (pygame.mixer.music.get_busy() == True ):
            continue
    Cur_Lock_State="closed"
    client.publish("LOCKASK",my_ip + "/CLOSED")
    conn = sqlite3.connect(dbName)
    req = conn.cursor()
    req.execute("UPDATE current_state SET Lock_Status = ? WHERE id=1",[Cur_Lock_State])
    conn.commit()
    conn.close()
    GPIO.output(4,True)
    if soundFlag == 1:
        pygame.mixer.music.load("/home/pi/Zaschitnoe_pole.mp3")
        pygame.mixer.music.play(loops=-1)
    
def Test_Access(Input):
    global dbName
    global my_ip
    global doorCheckTime
    conn = sqlite3.connect(dbName)
    req = conn.cursor()
    req.execute("SELECT Base_Status FROM current_state");
    S = req.fetchone()
    Status = S[0]
    req.execute("SELECT id FROM codes WHERE status = ? AND code = ?",[Status,Input])
    if (req.fetchone() != None):
        client.publish("LOCKASK",my_ip + "/CODE/RIGHT/" + Input)
        if(Cur_Lock_State == 'closed'):
            doorCheckTime = 10000
            Open_Door()
    else:
        client.publish("LOCKASK",my_ip + "/CODE/WRONG/" + Input)
        print "Wrong code!"
    conn.close()

soundFlag = 1

dbName = '/home/pi/LockDB.db'

mqtt_broker_ip = '192.168.0.103'
mqtt_broker_port = 1883

dbTime = 0
doorTime = 0
dbCheckTime = 1000
doorCheckTime = 0

curTime = millis()

port = serial.Serial("/dev/ttyAMA0", baudrate=9600, timeout=3.0)

GPIO.setmode(GPIO.BCM)
GPIO.setup(4,GPIO.OUT)

pygame.mixer.init()

Cur_Lock_State = ''
Cur_Base_State = ''

Inp_Seq = ''

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(mqtt_broker_ip, mqtt_broker_port, 5)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect((mqtt_broker_ip,mqtt_broker_port))
my_ip = s.getsockname()[0]
client.publish("LOCKASK",my_ip + '/PONG')
s.close()
client.loop_start()

conn = sqlite3.connect(dbName)
req = conn.cursor()
req.execute("SELECT Lock_Status FROM current_state")
S = req.fetchone()
Cur_Lock_State = S[0]
req.execute("SELECT Base_Status FROM current_state")
S = req.fetchone()
Cur_Base_State = S[0]
conn.close()

if (Cur_Lock_State == 'closed'):
    Close_Door()
else:
    doorCheckTime = 0
    Open_Door()

while 1:
    curTime = millis()
    byte = port.readline()
    if (byte != ''):
        if Cur_Lock_State == 'closed':
            RD_code = byte[:2]
            RD_type = byte[2:4]
            RD_value = string.strip(byte[4:])
            if(RD_type == 'KB'):			# Key pressed
                if(int(RD_value) == 10):
                    Inp_Seq = ''
                else: 
                    if(int(RD_value) == 11):
                        Test_Access(Inp_Seq)
                    else:
                        Inp_Seq += RD_value
            else:					# Card detected
                Inp_Seq = RD_value
                Test_Access(Inp_Seq)
        else:
            conn = sqlite3.connect(dbName)
            req = conn.cursor()
            req.execute("UPDATE current_state SET Lock_Status = 'closed' WHERE id=1")
            conn.commit()
            conn.close()
    else:
        Inp_Seq = ''
    if curTime >= (dbTime + dbCheckTime):
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("SELECT Lock_Status FROM current_state")
        LS = req.fetchone()
        req.execute("SELECT Base_Status FROM current_state")
        BS = req.fetchone()
        Cur_Base_State = BS[0]
        S1 = LS[0]
        conn.close();
        if(S1 != Cur_Lock_State):		# Status changed
            Cur_Lock_State = S1
            if(S1 == 'open'):			# Lock opened from server
                doorCheckTime = 10000
                Open_Door()
            else:				# Lock closed from server
                Close_Door()
        dbTime = curTime
    if curTime >= (doorTime + doorCheckTime) and Cur_Lock_State == 'open' and doorCheckTime != 0:
        Close_Door()
