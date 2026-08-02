#!/usr/bin/env python3
#import sys,os,io,numpy as np
from collections import defaultdict,Counter
try:sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
except Exception:pass
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from market_api import api
from tushare_api import get_pro
PRO=get_pro()
BDAY='20260730'
REPORT='_30d_mainline_report.txt'
