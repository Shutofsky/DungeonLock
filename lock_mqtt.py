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
import json
from netifaces import AF_INET

start_time = datetime.now()

params = dict()
codes = dict()

dbName = '/home/pi/LockDB.db'

dbTime = 0
doorTime = 0
dbCheckTime = 1000
doorCheckTime = 0
myIP = netifaces.ifaddresses('wlan0')[AF_INET][0]['addr']
gws = netifaces.gateways()
mqttIP = gws['default'][netifaces.AF_INET][0]
mqttPort = 1883
mqttFlag = False
client = mqtt.Client()

#port = serial.Serial("/dev/ttyAMA0", baudrate=9600, timeout=3.0)
port = serial.Serial("/dev/ttyAMA0", baudrate=9600)

GPIO.setmode(GPIO.BCM)
GPIO.setup(4,GPIO.OUT)

pygame.mixer.init()

Inp_Seq = ''

def millis():
    dt = datetime.now() - start_time
    ms = (dt.days * 24 * 60 * 60 + dt.seconds) * 1000 + dt.microseconds / 1000.0
    return ms

def onConnect(client, userdata, flags, rc):
    global myIP
    global mqttIP
    global mqttFlag
    client.subscribe("LOCK/#")
    mqttFlag = True
    print ("Connected to "+mqttIP) 

def onMessage(client, userdata, msg):
    global myIP
    global soundFlag
    global dbName
    global params
    global codes
    msgBody = msg.payload.decode('utf-8')
    commList = msgBody.split('/')
    if commList[0] != myIP and commList[0] != '*':
        return()
    if commList[1] == 'PING':
        client.publish("LOCKASK", myIP + '/PONG')
    elif commList[1] == 'OPEN':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("UPDATE params SET value = 'opened' WHERE name='lockState'")
        conn.commit()
        conn.close()
    elif commList[1] == 'CLOSE':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("UPDATE params SET value = 'closed' WHERE name='lockState'")
        conn.commit()
        conn.close()
    elif commList[1] == 'BLOCK':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("UPDATE params SET value = 'blocked' WHERE name='lockState'")
        conn.commit()
        conn.close()
    elif commList[1] == 'NOSOUND':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("UPDATE params SET value = 'False' WHERE name='isSound'")
        conn.commit()
        conn.close()
        params['isSound'] = 'False'
        pygame.mixer.music.stop()
    elif commList[1] == 'SOUND':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("UPDATE params SET value = 'True' WHERE name='isSound'")
        conn.commit()
        conn.close()
        params['isSound'] = 'True'
        if params['lockState'] == 'closed':
            pygame.mixer.music.play(loops=-1)
    elif commList[1] == 'STATUS':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("UPDATE params SET value = '?' WHERE name='baseState'",[commList[2].lower()])
        conn.commit()
        conn.close()
        params['baseState'] = commList[2].lower()
    elif commList[1] == 'GETID':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        jsStr = '{'
        for row in req.execute("SELECT * FROM codes"):
            val = row[1].split(',')
            jsStr += '"' + row[0] + '":['
            for valStr in val:
                jsStr += '"' + valStr + '",'
            jsStr = jsStr.rstrip(',') + '],'
        jsStr = jsStr.rstrip(',') + '}'
        codes = json.loads(jsStr)
        conn.close()
        client.publish("LOCKASK",myIP+"/IDLIST/"+jsStr)

def openDoor():
    global params
    global dbName
    global myIP
    global doorCheckTime
    global doorTime
    global Cur_Lock_State
    if params['isSound'] == True:
        pygame.mixer.music.stop()
        pygame.mixer.music.load("/home/pi/Zamknulo.mp3")
        pygame.mixer.music.play()
    params['lockState']="opened"
    conn = sqlite3.connect(dbName)
    req = conn.cursor()
    req.execute("UPDATE params SET value = 'opened' WHERE name='lockState'")
    conn.commit()
    conn.close()
    GPIO.output(4,False)
    if mqttFlag:
        client.publish("LOCKASK",myIP + "/OPENED")
    doorTime = millis()

def closeDoor():
    global dbName
    global myIP
    global doorCheckTime
    global doorTime
    global params
    global mqttFlag
    if params['isSound'] == 'True':
        pygame.mixer.music.load("/home/pi/Zamknulo.mp3")
        pygame.mixer.music.play()
        while (pygame.mixer.music.get_busy() == True ):
            continue
    params['lockState']="closed"
    conn = sqlite3.connect(dbName)
    req = conn.cursor()
    req.execute("UPDATE params SET value = 'closed' WHERE name = 'lockState'")
    conn.commit()
    conn.close()
    GPIO.output(4,True)
    if mqttFlag:
        client.publish("LOCKASK",myIP + "/CLOSED")
    if params['isSound'] == True:
        pygame.mixer.music.load("/home/pi/Zaschitnoe_pole.mp3")
        pygame.mixer.music.play(loops=-1)
    
def testAccess(Input):
    global dbName
    global myIP
    global doorCheckTime
    global params
    global codes
    global mqttFlag
    if params['lockState'] == 'blocked':
        if mqttFlag:
            client.publish("LOCKASK", myIP + "/CODE/BLOCK/" + Input)
        return()
    if Input not in codes.keys():
        if mqttFlag:
            client.publish("LOCKASK", myIP + "/CODE/GLOBALWRONG/" + Input)
        return ()
    if params['baseState'] not in codes[Input]:
        if mqttFlag:
            client.publish("LOCKASK", myIP + "/CODE/STATUSWRONG/" + Input)
        return ()
    else:
        if mqttFlag:
            client.publish("LOCKASK", myIP + "/CODE/RIGHT/" + Input)
        if(params['lockState'] == 'closed'):
            doorCheckTime = 10000
            openDoor()

def serialAsk():
    global dbName
    global params
    while True:
        portByte = port.readline()
        byte = portByte.decode('utf-8')
        if (byte != ''):
            if params['lockState'] == 'closed':
                RDType = byte[2:4]
                RDValue = str(byte[4:])
                RDValue = RDValue.strip()
                if(RDType == 'KB'):			# Key pressed
                    if(int(RDValue) == 10):
                        inpSeq = ''
                    else: 
                        if(int(RDValue) == 11):
                            testAccess(inpSeq)
                        else:
                            inpSeq += RDValue
                else:					# Card detected
                    inpSeq = RDValue
                    testAccess(inpSeq)
                    inpSeq = ''
            else:
                conn = sqlite3.connect(dbName)
                req = conn.cursor()
                req.execute("UPDATE params SET value = 'closed' WHERE name = 'lockState'")
                conn.commit()
                conn.close()

def checkDB():
    global dbTime
    global dbCheckTime
    global doorTime
    global doorCheckTime
    global dbName
    global params
    global codes
    global params
    curTime = millis()
    if curTime >= (dbTime + dbCheckTime):
        oldState = params['lockState']
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        jsStr = '{'
        for row in req.execute("SELECT * FROM params"):
            jsStr += '"' + row[0] + '":"' + row[1] + '",'
        jsStr = jsStr.rstrip(',') + '}'
        params = json.loads(jsStr)
        jsStr = '{'
        for row in req.execute("SELECT * FROM codes"):
            val = row[1].split(',')
            jsStr += '"' + row[0] + '":['
            for valStr in val:
                jsStr += '"' + valStr + '",'
            jsStr = jsStr.rstrip(',') + '],'
        jsStr = jsStr.rstrip(',') + '}'
        codes = json.loads(jsStr)
        conn.close()
        if(oldState != params['lockState']):		# Status changed
            if(params['lockState'] == 'opened'):			# Lock opened from server
                doorCheckTime = 0
                openDoor()
            else:				# Lock closed from server
                closeDoor()
        dbTime = curTime
    if curTime >= (doorTime + doorCheckTime) and params['lockState'] == 'opened' and doorCheckTime != 0:
        closeDoor()

curTime = millis()

def mqttSetup():
    client.on_connect = onConnect
    client.on_message = onMessage
    try:
        client.connect(mqttIP, mqttPort, 5)
    except socket.error:
        print ("Can not connect")
    else: 
        client.loop_start()


conn = sqlite3.connect(dbName)
req = conn.cursor()
jsStr = '{'
for row in req.execute("SELECT * FROM params"):
    jsStr += '"'+row[0]+'":"'+row[1]+'",'
jsStr = jsStr.rstrip(',')+'}'
params = json.loads(jsStr)
jsStr = '{'
for row in req.execute("SELECT * FROM codes"):
    val = row[1].split(',')
    jsStr += '"' + row[0] + '":['
    for valStr in val:
        jsStr += '"'+valStr+'",'
    jsStr = jsStr.rstrip(',')+'],'
jsStr = jsStr.rstrip(',')+'}'
codes = json.loads(jsStr)
conn.close()

if (params['lockState'] == 'closed' or params['lockState'] == 'blocked'):
    closeDoor()
else:
    doorCheckTime = 0
    openDoor()

print (myIP)

portAsk = threading.Thread(name='seraiAsk', \
                               target=serialAsk)

checkDBase = threading.Thread(name='checkDB', \
                               target=checkDB)

mqttInit = threading.Thread(name='mqttInit', \
                               target=mqttSetup)


mqttInit.start()
portAsk.start()
checkDBase.start()