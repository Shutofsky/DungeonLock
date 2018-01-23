#!/usr/bin/python
import RPi.GPIO as GPIO
import serial
import time
from datetime import datetime
from datetime import timedelta
import sqlite3
import pygame
import paho.mqtt.client as mqtt
import socket
import threading
import netifaces
from netifaces import AF_INET


start_time = datetime.now()

soundFlag = 1

dbName = '/home/pi/LockDB.db'

dbTime = 0
doorTime = 0
dbCheckTime = 1000
doorCheckTime = 0
my_ip = netifaces.ifaddresses('wlan0')[AF_INET][0]['addr']
gws = netifaces.gateways()
mqttIP = gws['default'][netifaces.AF_INET][0]
mqttPort = 1883
client = mqtt.Client()

#port = serial.Serial("/dev/ttyAMA0", baudrate=9600, timeout=3.0)
port = serial.Serial("/dev/ttyAMA0", baudrate=9600)

GPIO.setmode(GPIO.BCM)
GPIO.setup(4,GPIO.OUT)

pygame.mixer.init()

Cur_Lock_State = ''
Cur_Base_State = ''

Inp_Seq = ''


def millis():
    dt = datetime.now() - start_time
    ms = (dt.days * 24 * 60 * 60 + dt.seconds) * 1000 + dt.microseconds / 1000.0
    return ms

def on_connect(client, userdata, flags, rc):
    global my_ip
    global mqttIP
    client.subscribe("LOCK/#")
    print ("Connected to "+mqttIP) 

def on_message(client, userdata, msg):
    global my_ip
    global soundFlag
    global dbName
    global Cur_Lock_State
    msgBody = msg.payload.decode('utf-8')
    commList = msgBody.split('/')
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
        print (S)
        req.execute("UPDATE current_state SET Base_Status = ? WHERE id=1",[S])
        conn.commit()
        conn.close()
    elif commList[1] == 'GETID':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        for idCode in req.execute("SELECT DISTINCT code FROM \
                                    codes ORDER BY code"):
            req_stat = conn.cursor()
            statStr = ''
            for idStatus in req_stat.execute("SELECT status FROM codes \
                                              WHERE code = ?",[idCode[0]]):
                statStr += '/'+idStatus[0] 
            print ("CODE = "+idCode[0]+" staus = "+statStr)
            client.publish("LOCKASK",my_ip+"/IDLIST/"+idCode[0]+statStr)
            time.sleep(0.2)
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
    conn = sqlite3.connect(dbName)
    req = conn.cursor()
    req.execute("UPDATE current_state SET Lock_Status = ? WHERE id=1",[Cur_Lock_State])
    conn.commit()
    conn.close()
    GPIO.output(4,True)
    client.publish("LOCKASK",my_ip + "/CLOSED")
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
    req.execute("SELECT code FROM codes WHERE status = ? AND code = ?",[Status,Input])
    if (req.fetchone() != None):
        client.publish("LOCKASK",my_ip + "/CODE/RIGHT/" + Input)
        if(Cur_Lock_State == 'closed'):
            doorCheckTime = 10000
            Open_Door()
    else:
        client.publish("LOCKASK",my_ip + "/CODE/WRONG/" + Input)
        print ("Wrong code!")
    conn.close()

def serialAsk():
    global dbName
    while True:
        portByte = port.readline()
        byte = portByte.decode('utf-8')
        print (byte)
        if (byte != ''):
            if Cur_Lock_State == 'closed':
                RD_code = byte[:2]
                RD_type = byte[2:4]
                RD_value = str(byte[4:])
                RD_value = RD_value.strip()
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
                    Inp_Seq = ''
            else:
                conn = sqlite3.connect(dbName)
                req = conn.cursor()
                req.execute("UPDATE current_state SET Lock_Status = 'closed' WHERE id=1")
                conn.commit()
                conn.close()
   
def checkDB():
    global dbTime
    global dbCheckTime
    global doorTime
    global doorCheckTime
    global dbName
    global Cur_Base_State
    global Cur_Lock_State
    curTime = millis()
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
                doorCheckTime = 0
                Open_Door()
            else:				# Lock closed from server
                Close_Door()
        dbTime = curTime
    if curTime >= (doorTime + doorCheckTime) and Cur_Lock_State == 'open' and doorCheckTime != 0:
        Close_Door()

curTime = millis()

def mqttSetup():
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(mqttIP, mqttPort, 5)
    except socket.error:
        print ("Can not connect")
    else: 
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

print (my_ip)

portAsk = threading.Thread(name='seraiAsk', \
                               target=serialAsk)

checkDBase = threading.Thread(name='checkDB', \
                               target=checkDB)

mqttInit = threading.Thread(name='mqttInit', \
                               target=mqttSetup)


mqttInit.start()
portAsk.start()
checkDBase.start()