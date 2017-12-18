from gurobipy import *
import numpy as np
import collections
import importlib
import math
from schedule_dag import ScheduleDAG
from printers import *
from solution import Solution
import sys

if __name__ == '__main__':
    if (len(sys.argv) != 6):
        print ("Usage: ", sys.argv[0], " <DAG file> <HW file> <latency file> <time limit in mins> <burst_size>")
        exit(1)
    elif (len(sys.argv) == 6):
        input_file   = sys.argv[1]
        hw_file      = sys.argv[2]
        latency_file = sys.argv[3]
        minute_limit = int(sys.argv[4])
        burst_size = int(sys.argv[5])
    
    # Input specification
    input_spec = importlib.import_module(input_file, "*")
    hw_spec    = importlib.import_module(hw_file, "*")
    latency_spec=importlib.import_module(latency_file, "*")
    input_spec.action_fields_limit = hw_spec.action_fields_limit
    input_spec.match_unit_limit    = hw_spec.match_unit_limit
    input_spec.match_unit_size     = hw_spec.match_unit_size
    input_spec.action_proc_limit   = hw_spec.action_proc_limit
    input_spec.match_proc_limit    = hw_spec.match_proc_limit

    G = ScheduleDAG()
    G.create_dag(input_spec.nodes, input_spec.edges, latency_spec)
    cpath, cplat = G.critical_path()

    match_nodes = G.nodes(select='match')
    action_nodes = G.nodes(select='action')

    match_key_size = 0
    action_key_size = 0

    for node in match_nodes:
        match_key_size += G.node[node]['key_width']
    
    for node in action_nodes:
        action_key_size += G.node[node]['num_fields']
  
    print ("match_usage, action_usage", match_key_size, action_key_size)

    