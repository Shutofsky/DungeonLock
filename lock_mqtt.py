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
#mqttIP = gws['default'][netifaces.AF_INET][0]
mqttIP = '192.168.0.200'
mqttPort = 1883
mqttFlag = False

port = serial.Serial("/dev/ttyS0", baudrate=9600)
#port = serial.Serial("/dev/ttyAMA0", baudrate=9600)

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
        client.publish("LOCKASK",myIP+"/NOSOUND")
    elif commList[1] == 'SOUND':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("UPDATE params SET value = 'True' WHERE name='isSound'")
        conn.commit()
        conn.close()
        params['isSound'] = 'True'
        if params['lockState'] == 'closed':
            pygame.mixer.music.play(loops=-1)
        client.publish("LOCKASK",myIP+"/SOUND")
    elif commList[1] == 'STATUS':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        print(commList[2].lower())
        req.execute("UPDATE params SET value = ? WHERE name='baseState'",[commList[2].lower()])
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
    elif commList[1] == 'GETDB':
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        jsStr = '{'
        for row in req.execute("SELECT name, value FROM params"):
            jsStr += '"' + row[0] + '":"' + row[1] +'",'
        jsStr += '"codes":{'
        for row in req.execute("SELECT * FROM codes"):
            val = row[1].split(',')
            jsStr += '"' + row[0] + '":['
            for valStr in val:
                jsStr += '"' + valStr.strip() + '",'
            jsStr = jsStr.rstrip(',') + '],'
        jsStr = jsStr.rstrip(',') + '}}'
        conn.close()
        client.publish("LOCKASK",myIP+"/LOCKDATA/"+jsStr)
    elif commList[1] == 'DELALLID':
        del(codes)
        codes = dict()
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("DELETE FROM codes")
        conn.commit()
        conn.close()
    elif commList[1] == 'DELID':
        del(codes[commList[2]])
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("DELETE FROM codes WHERE idCode = ?",[commList[2]])
        conn.commit()
        conn.close()
    elif commList[1] == 'ADDID':
        codes[commList[2]] = commList[3]
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("INSERT INTO codes VALUES (?,?)",[commList[2],commList[3]])
        conn.commit()
        conn.close()
    elif commList[1] == 'CHGID':
        codes[commList[2]] = commList[3]
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        req.execute("UPDATE codes SET statusList = ? \
                     WHERE idCode = ?",[commList[3],commList[2]])
        conn.commit()
        conn.close()
    elif commList[1] == 'SETPARMS':
        params = json.loads(commList[2])
        conn = sqlite3.connect(dbName)
        req = conn.cursor()
        for parName in params.keys():
            req.execute("UPDATE params SET value = ? \
                         WHERE name = ?",[params[parName],parName])
        conn.commit()
#        if params['lockState'] == 'opened':
#            openDoor()
#        else:
#            closeDoor(params['lockState'])
        conn.close()
        
def openDoor(openTime):
    global params
    global dbName
    global myIP
    global doorCheckTime
    global doorTime
    if params['isSound'] == 'True':
        pygame.mixer.music.stop()
        pygame.mixer.music.load("/home/pi/Zamknulo.mp3")
        pygame.mixer.music.play()
        while (pygame.mixer.music.get_busy() == True ):
            continue
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
    doorCheckTime = openTime * 1000

def closeDoor(clStat):
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
    params['lockState']=clStat
    conn = sqlite3.connect(dbName)
    req = conn.cursor()
    req.execute("UPDATE params SET value = ? WHERE name = 'lockState'",\
                [clStat])
    conn.commit()
    conn.close()
    if mqttFlag:
        if clStat == 'closed':
            client.publish("LOCKASK",myIP + "/CLOSED")
        else:
            client.publish("LOCKASK",myIP + "/BLOCKED")
    GPIO.output(4,True)
    if params['isSound'] == 'True':
        pygame.mixer.music.load("/home/pi/Zaschitnoe_pole.mp3")
        pygame.mixer.music.play(loops=-1)
    doorTime = 0
    doorCheckTime = 0

def testAccess(Input):
    global dbName
    global myIP
    global doorCheckTime
    global params
    global codes
    global mqttFlag
    if Input not in codes.keys():
        if mqttFlag:
            client.publish("LOCKASK", myIP + "/CODE/GLOBALWRONG/" + Input)
        return()
    if params['baseState'] not in codes[Input]:
        if mqttFlag:
            client.publish("LOCKASK", myIP + "/CODE/STATUSWRONG/" + Input)
        return()
    else:
        if mqttFlag:
            client.publish("LOCKASK", myIP + "/CODE/RIGHT/" + Input)
        if(params['lockState'] == 'closed'):
            openDoor(10)

def serialAsk():
    global dbName
    global params
    while True:
        portByte = port.readline()
        byte = portByte.decode('utf-8')
        if (byte != ''):
            RDType = byte[2:4]
            RDValue = str(byte[4:])
            RDValue = RDValue.strip()
            if params['lockState'] == 'closed':
                if(RDType == 'KB'):			# Key pressed
                    if(int(RDValue) == 10):
                        inpSeq = ''
                    else: 
                        if(int(RDValue) == 11):
                            print (inpSeq)
                            testAccess(inpSeq)
                        else:
                            inpSeq += RDValue
                else:					# Card detected
                    inpSeq = RDValue
                    print (inpSeq)
                    testAccess(inpSeq)
                    inpSeq = ''
            elif(RDType == 'CD'):
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
    pygame.mixer.music.stop()
    pygame.mixer.music.load("/home/pi/Zaschitnoe_pole.mp3")
    while True:
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
            if(oldState != params['lockState']):	# Status changed
                if(params['lockState'] == 'opened'):	# Lock opened from server
                    openDoor(0)
                else:				# Lock closed from server
                    closeDoor(params['lockState'])
            dbTime = curTime
        if curTime >= (doorTime + doorCheckTime) and \
            params['lockState'] == 'opened' and doorCheckTime != 0:
            closeDoor('closed')

curTime = millis()

def mqttSetup():
    global client
    print ('Connecting to '+mqttIP)
    try:
        client.connect(mqttIP, mqttPort, 5)
    except:
        print ("Can not connect")
    else: 
        print ('Loop starting')
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
    closeDoor(params['lockState'])
else:
    doorCheckTime = 0
    openDoor(0)

print (myIP)

client = mqtt.Client()
client.on_connect = onConnect
client.on_message = onMessage


portAsk = threading.Thread(name='seraiAsk', \
                               target=serialAsk)

checkDBase = threading.Thread(name='checkDB', \
                               target=checkDB)

mqttInit = threading.Thread(name='mqttInit', \
                               target=mqttSetup)


mqttInit.start()
portAsk.start()
checkDBase.start()