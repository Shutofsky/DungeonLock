#!/usr/bin/python3
# coding: utf-8

import serial
 
ser = serial.Serial("/dev/ttyS0")
ser.baudrate = 9600
 
while True :
  line = ser.readline()
  print (line)