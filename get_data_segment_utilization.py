import sys
import importlib
import json
import math

def compute_action_utilization(nodes, time_of_op, latency_spec, proc_count, match_dict):
    
    # iterate over nodes whether evrey node has been allocated a timeslot
    for node in nodes:
        if node.endswith("_MATCH"):
            if node not in match_dict:
                print(node)
    
    time_stamp = []
    match_nodes = []
    m_action_nodes = []
    for node in time_of_op:
        if node.endswith("_MATCH"):
            if node not in match_nodes:
                match_nodes.append(node)
        
        ts = time_of_op[node]
        if ts not in time_stamp:
            time_stamp.append(ts)
    
    max_ts = max(time_stamp)

    scratch_utilization = []
    count_scratch_utilization = []

    node_result_utilization = {}
    for i in range(max_ts+1):
        scratch_utilization.append(0)
        count_scratch_utilization.append(0)
    counter = 0
    h_counter = 0
    for node in match_nodes:
        ts_init = time_of_op[node]
        action_node = node.replace("_MATCH", "_ACTION")
        #print (node, action_node, time_of_op[node], time_of_op[action_node], match_dict[node] )
        if action_node in time_of_op:
            if time_of_op[action_node] - time_of_op[node] > latency_spec.dM:
                counter += 1
                for i in range(time_of_op[node]+latency_spec.dM+1, time_of_op[action_node]):

                    count_scratch_utilization[i] += 1
                    byte_util = match_dict[node] + 10

                    util = 0
                    if byte_util%8 != 0:
                        util += 1
                    
                    util += int(byte_util/8)
                    scratch_utilization[i] += util

        else :
            print(action_node)
    
    print(counter)
    #print(count_scratch_utilization)
    #print(scratch_utilization)
    real_scratch_utilization = []
    count_real_scratch_utilization = []
    for i in range(proc_count):
        real_scratch_utilization.append(0)
        count_real_scratch_utilization.append(0)

    for i in range(max_ts+1):
        k = i /proc_count
        r = int(i % proc_count)
        real_scratch_utilization[r] += scratch_utilization[i]
        count_real_scratch_utilization[r] += count_scratch_utilization[i]
    
    print("Counter", counter)
    print( count_real_scratch_utilization )
    print(max_ts+1)
    print(max(count_scratch_utilization))
    print(max(scratch_utilization))
    return (max(real_scratch_utilization))


if __name__ == "__main__" :
    if (len(sys.argv) <= 4 ) :
        print("Usage: ", sys.argv[0], "<DAG_file> <lt_file> <soln_json> <match_json>")
        exit(1)
    else :
        input_graph = importlib.import_module(sys.argv[1], "*")
        latency_spec = importlib.import_module(sys.argv[2], "*")
        json_file1 = sys.argv[3]
        json_file2 = sys.argv[4]

    with open(json_file2) as data_file: 
        match_dict = json.load(data_file)

    with open(json_file1) as data_file: 
        json_data = json.load(data_file)


    time_of_op = json_data['time_of_op']
    proc_count = json_data['proc_count']

    compute_action_utilization(input_graph.nodes, time_of_op, latency_spec, proc_count, match_dict)
   
    