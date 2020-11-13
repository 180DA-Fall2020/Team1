import sys
import time
import math
import IMU
import datetime
import os
import pandas as pd 
import utils 

SAMPLE_RATE_HZ = 100
QUATERNION_SCALE = (1.0 / (1<<14))

ACC_LPF_FACTOR = 0.4    # Low pass filter constant for accelerometer
MAG_LPF_FACTOR = 0.4    # Low pass filter constant magnetometer
ACC_MEDIANTABLESIZE = 9         # Median filter table size for accelerometer. Higher = smoother but a longer delay
MAG_MEDIANTABLESIZE = 9         # Median filter table size for magnetometer. Higher = smoother but a longer delay

magXmin =  0
magYmin =  0
magZmin =  0
magXmax =  0
magYmax =  0
magZmax =  0

oldXMagRawValue = 0
oldYMagRawValue = 0
oldZMagRawValue = 0
oldXAccRawValue = 0
oldYAccRawValue = 0
oldZAccRawValue = 0

#Setup the tables for the median filter. Fill them all with '1' so we dont get devide by zero error
acc_medianTable1X = [1] * ACC_MEDIANTABLESIZE
acc_medianTable1Y = [1] * ACC_MEDIANTABLESIZE
acc_medianTable1Z = [1] * ACC_MEDIANTABLESIZE
acc_medianTable2X = [1] * ACC_MEDIANTABLESIZE
acc_medianTable2Y = [1] * ACC_MEDIANTABLESIZE
acc_medianTable2Z = [1] * ACC_MEDIANTABLESIZE
mag_medianTable1X = [1] * MAG_MEDIANTABLESIZE
mag_medianTable1Y = [1] * MAG_MEDIANTABLESIZE
mag_medianTable1Z = [1] * MAG_MEDIANTABLESIZE
mag_medianTable2X = [1] * MAG_MEDIANTABLESIZE
mag_medianTable2Y = [1] * MAG_MEDIANTABLESIZE
mag_medianTable2Z = [1] * MAG_MEDIANTABLESIZE

def collect(): 
    global ACC_LPF_FACTOR, ACC_MEDIANTABLESIZE, oldXAccRawValue, oldYAccRawValue, oldZAccRawValue
    global MAG_LPF_FACTOR, MAG_MEDIANTABLESIZE, oldXMagRawValue, oldYMagRawValue, oldZMagRawValue
    global acc_medianTable1X, acc_medianTable1Y, acc_medianTable1Z, acc_medianTable2X, acc_medianTable2Y, acc_medianTable2Z
    global mag_medianTable1X, mag_medianTable1Y, mag_medianTable1Z, mag_medianTable2X, mag_medianTable2Y, mag_medianTable2Z

    #Read the accelerometer,gyroscope and magnetometer values
    ACCx = IMU.readACCx()
    ACCy = IMU.readACCy()
    ACCz = IMU.readACCz()
    GYRx = IMU.readGYRx()
    GYRy = IMU.readGYRy()
    GYRz = IMU.readGYRz()
    MAGx = IMU.readMAGx()
    MAGy = IMU.readMAGy()
    MAGz = IMU.readMAGz()

    #Apply compass calibration
    MAGx -= (magXmin + magXmax) /2
    MAGy -= (magYmin + magYmax) /2
    MAGz -= (magZmin + magZmax) /2

    ###############################################
    #### Apply low pass filter ####
    ###############################################
    ACCx =  ACCx  * ACC_LPF_FACTOR + oldXAccRawValue*(1 - ACC_LPF_FACTOR);
    ACCy =  ACCy  * ACC_LPF_FACTOR + oldYAccRawValue*(1 - ACC_LPF_FACTOR);
    ACCz =  ACCz  * ACC_LPF_FACTOR + oldZAccRawValue*(1 - ACC_LPF_FACTOR);
    MAGx =  MAGx  * MAG_LPF_FACTOR + oldXMagRawValue*(1 - MAG_LPF_FACTOR);
    MAGy =  MAGy  * MAG_LPF_FACTOR + oldYMagRawValue*(1 - MAG_LPF_FACTOR);
    MAGz =  MAGz  * MAG_LPF_FACTOR + oldZMagRawValue*(1 - MAG_LPF_FACTOR);

    oldXAccRawValue = ACCx
    oldYAccRawValue = ACCy
    oldZAccRawValue = ACCz
    oldXMagRawValue = MAGx
    oldYMagRawValue = MAGy
    oldZMagRawValue = MAGz

    #########################################
    #### Median filter for accelerometer ####
    #########################################
    # cycle the table
    for x in range (ACC_MEDIANTABLESIZE-1,0,-1 ):
        acc_medianTable1X[x] = acc_medianTable1X[x-1]
        acc_medianTable1Y[x] = acc_medianTable1Y[x-1]
        acc_medianTable1Z[x] = acc_medianTable1Z[x-1]

    # Insert the lates values
    acc_medianTable1X[0] = ACCx
    acc_medianTable1Y[0] = ACCy
    acc_medianTable1Z[0] = ACCz

    # Copy the tables
    acc_medianTable2X = acc_medianTable1X[:]
    acc_medianTable2Y = acc_medianTable1Y[:]
    acc_medianTable2Z = acc_medianTable1Z[:]

    # Sort table 2
    acc_medianTable2X.sort()
    acc_medianTable2Y.sort()
    acc_medianTable2Z.sort()

    # The middle value is the value we are interested in
    ACCx = acc_medianTable2X[int(ACC_MEDIANTABLESIZE/2)];
    ACCy = acc_medianTable2Y[int(ACC_MEDIANTABLESIZE/2)];
    ACCz = acc_medianTable2Z[int(ACC_MEDIANTABLESIZE/2)];

    #########################################
    #### Median filter for magnetometer ####
    #########################################
    # cycle the table
    for x in range (MAG_MEDIANTABLESIZE-1,0,-1 ):
        mag_medianTable1X[x] = mag_medianTable1X[x-1]
        mag_medianTable1Y[x] = mag_medianTable1Y[x-1]
        mag_medianTable1Z[x] = mag_medianTable1Z[x-1]

    # Insert the latest values
    mag_medianTable1X[0] = MAGx
    mag_medianTable1Y[0] = MAGy
    mag_medianTable1Z[0] = MAGz

    # Copy the tables
    mag_medianTable2X = mag_medianTable1X[:]
    mag_medianTable2Y = mag_medianTable1Y[:]
    mag_medianTable2Z = mag_medianTable1Z[:]

    # Sort table 2
    mag_medianTable2X.sort()
    mag_medianTable2Y.sort()
    mag_medianTable2Z.sort()

    # The middle value is the value we are interested in
    MAGx = mag_medianTable2X[int(MAG_MEDIANTABLESIZE/2)];
    MAGy = mag_medianTable2Y[int(MAG_MEDIANTABLESIZE/2)];
    MAGz = mag_medianTable2Z[int(MAG_MEDIANTABLESIZE/2)];

    ##################### END Tilt Compensation ########################
    
    accel = [ACCx, ACCy, ACCz]
    mag = [MAGx, MAGy, MAGz] 
    gyro = [GYRx, GYRy, GYRz]
    euler = [0, 0, 0]
    quaternion = [0, 0, 0, 0]
    lin_accel = [0, 0, 0]
    gravity = [0, 0, 0]

    return accel + mag + gyro + euler + quaternion + lin_accel + gravity 

IMU.detectIMU()     #Detect if BerryIMU is connected.
if(IMU.BerryIMUversion == 99):
    print(" No BerryIMU found... exiting ")
    sys.exit()
IMU.initIMU()       #Initialise the accelerometer, gyroscope and compass

i = 0
header = ["time_ms", "delta_ms"] + utils.get_sensor_headers()

filename = input("Name the folder where data will be stored: ")
if not os.path.exists(filename):
    os.mkdir(filename + '/')
starting_index = int(input("What number should we start on? "))

duration_s = float(input("Please input how long should a sensor trace be in seconds (floats OK): "))

i = starting_index

while True:
    input("Collecting file " + str(i)+ ". Press Enter to continue...")
    start = datetime.datetime.now()
    elapsed_ms = 0
    previous_elapsed_ms = 0

    data = []
    while elapsed_ms < duration_s * 1000:
        row = [elapsed_ms, int(elapsed_ms - previous_elapsed_ms)] + collect() # heading, roll, pitch, sys, gyro, accel, mag]
        data.append(row)
        previous_elapsed_ms = elapsed_ms
        elapsed_ms = (datetime.datetime.now() - start).total_seconds() * 1000

    file_name = filename + "/" + filename + '{0:03d}'.format(i) + ".csv"
    df = pd.DataFrame(data, columns = header)
    df.to_csv(file_name, header=True)
    i += 1