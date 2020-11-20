#!/usr/bin/env python
from distutils.core import setup, Extension 

setup(
    name='Virtual Hole in the Wall', 
    url='https://github.com/180D-FW-2020/Team1',
    install_requires=[
        'pandas==0.23.3', 
        'joblib==0.17.0', 
        'SpeechRecognition==3.8.1', 
        'numpy==1.14.0', 
        'smbus2==0.3.0', 
        'paho_mqtt==1.5.1', 
        'scikit_learn==0.19.0', 
        'opencv-python==3.3.1'
        ] 
)

